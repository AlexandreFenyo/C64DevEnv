#!/usr/bin/env python3
"""importworld.py - importe la carte du monde (page HTML de l'utilisateur) en
libc64/world/world.txt.

Usage : importworld.py CARTE.html [world.txt]

La page génère le monde en JavaScript (graine fixe : résultat déterministe) :
on exécute son script avec node, sans la partie rendu (canvas), et on relève
le tableau `monde` : une case = un code de tile, ou {tile, colorRam} quand la
Color RAM est imposée (couleur CSS « #rrggbb », convertie en index C64 grâce
à la palette de libc64/tileset/tileset.txt).

world.txt est ensuite la source du monde (tools/mkworld.py le compresse) :
il suffit de réimporter quand la carte change. node n'est nécessaire qu'ici.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILESET = os.path.join(ROOT, "libc64", "tileset", "tileset.txt")

EXTRACT_JS = r"""
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
let js = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
const cut = js.indexOf('// 12. RENDU');
if (cut < 0) { console.error('section « // 12. RENDU » introuvable dans le script'); process.exit(2); }
js = js.slice(0, js.lastIndexOf('\n', cut));
js += '\n;globalThis.__out = { W: MONDE_W, H: MONDE_H, monde };';
const ctx = { console, Math, Set, Map, Object, Array, JSON };
vm.createContext(ctx);
vm.runInContext(js, ctx);
const { W, H, monde } = ctx.__out;
const cells = monde.map(r => r.map(c => (typeof c === 'object' && c !== null) ? [c.tile, c.colorRam] : c));
process.stdout.write(JSON.stringify({ W, H, cells }));
"""


def palette():
    """{"#rrggbb": index C64} depuis la section 2 de tileset.txt."""
    pal = {}
    for line in open(TILESET, encoding="utf-8"):
        m = re.match(r"^\s+\w+\s+couleur\s+(\d+)\s+#([0-9A-Fa-f]{6})", line)
        if m:
            pal["#" + m.group(2).lower()] = int(m.group(1))
    return pal


def main(argv):
    if not 1 <= len(argv) <= 2:
        sys.exit(__doc__.split("\n\n")[1])
    html = argv[0]
    out = argv[1] if len(argv) > 1 else os.path.join(ROOT, "libc64", "world", "world.txt")
    if not shutil.which("node"):
        sys.exit("importworld.py: node est nécessaire pour exécuter le script de la carte (sudo apt install nodejs)")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(EXTRACT_JS)
        js = f.name
    try:
        r = subprocess.run(["node", js, html], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    finally:
        os.unlink(js)
    if r.returncode != 0:
        sys.exit("importworld.py: échec du script de la carte :\n" + r.stderr)
    world = json.loads(r.stdout)
    w, h, cells = world["W"], world["H"], world["cells"]
    pal = palette()
    values, index, rows = [], {}, []
    for y, row in enumerate(cells):
        if len(row) != w:
            sys.exit("importworld.py: ligne %d : %d cases au lieu de %d" % (y, len(row), w))
        out_row = []
        for x, c in enumerate(row):
            if isinstance(c, list):
                color = pal.get(str(c[1]).lower())
                if color is None:
                    sys.exit("importworld.py: case (%d, %d) : couleur %s absente de la palette" % (x, y, c[1]))
                v = (int(c[0]), color)
            else:
                v = (int(c), None)
            if v not in index:
                index[v] = len(values)
                values.append(v)
            out_row.append(index[v])
        rows.append(out_row)
    if len(values) > 255:
        sys.exit("importworld.py: %d valeurs de case distinctes : 255 au plus" % len(values))
    with open(out, "w", encoding="utf-8") as f:
        f.write("# Monde du jeu : importé par tools/importworld.py depuis %s\n" % os.path.basename(html))
        f.write("# (réimporter plutôt que modifier à la main ; tools/mkworld.py le compresse).\n")
        f.write("# W/H : taille en tiles. C <index> <code tile> <Color RAM imposée, - = celle du tile>\n")
        f.write("# R <ligne> : une ligne du monde, index de valeur de case en hexadécimal (2 chiffres par case).\n")
        f.write("W %d\nH %d\n" % (w, h))
        for i, (code, color) in enumerate(values):
            f.write("C %02X %02X %s\n" % (i, code, "-" if color is None else "%d" % color))
        for y, row in enumerate(rows):
            f.write("R %03d %s\n" % (y, "".join("%02X" % v for v in row)))
    print("importworld.py: monde %dx%d, %d valeurs de case -> %s" % (w, h, len(values), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
