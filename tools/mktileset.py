#!/usr/bin/env python3
"""mktileset.py - génère les données du jeu de caractères de libc64/tileset.

Usage : mktileset.py [--check] SPEC.txt DATA.s TILES.h TILES.inc

Lit la description du tileset (libc64/tileset/tileset.txt : configuration
VIC-II, palette, palettes P01..., tiles « $CODE NOM PALETTE 8 octets ») et
écrit :
  DATA.s     motifs (_tileset_glyphs, codes TILE_FIRST..TILE_LAST, trous à 0)
             et Color RAM par défaut de chaque code (_tileset_colors) ;
  TILES.h    constantes C : TILE_<NOM>, couleurs TC_<NOM>, registres globaux ;
  TILES.inc  les mêmes pour l'assembleur.

Color RAM par défaut d'un tile : STD -> couleur du bit 1 (0-7) ; MC -> 8 +
couleur du couple 11 (le bit 3 rend la case multicolore). Contrôles : erreur
si un tile est mal formé ; avertissement (et couleur 0-7 la plus proche en
RGB) si une palette demande en Color RAM une couleur 8-15, inaccessible.
--check : n'écrit rien, renvoie 1 si les fichiers générés ne sont pas à jour.
"""
import os
import re
import sys

TILE_RE = re.compile(r"^\$([0-9A-Fa-f]{2})\s+(\w+)\s+(P\d\d)\s+((?:[01]{8}\s*){8})$")
PAL_RE = re.compile(r"^\s+(P\d\d)\s+(STD|MC)\s+(.*)$")
COLOR_RE = re.compile(r"^\s+(\w+)\s+couleur\s+(\d+)\s+#([0-9A-Fa-f]{6})")
REG_RE = re.compile(r"^\s+\$(D02[123])\s*=\s*(\d+)")
HEADER = "Généré par tools/mktileset.py depuis libc64/tileset/tileset.txt : ne pas modifier."


def parse(path):
    colors, pals, tiles, regs, errors, total = {}, {}, [], {}, [], None
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if m := TILE_RE.match(line):
            code = int(m.group(1), 16)
            rows = [int(b, 2) for b in m.group(4).split()]
            tiles.append((code, m.group(2), m.group(3), rows, n))
        elif line.startswith("$") and re.match(r"^\$[0-9A-Fa-f]{2}\s", line):
            errors.append("ligne %d : tile mal formé (8 octets binaires attendus) : %s" % (n, line))
        elif m := PAL_RE.match(line):
            pals[m.group(1)] = (m.group(2), dict(kv.split("=") for kv in m.group(3).split()))
        elif m := COLOR_RE.match(line):
            colors[m.group(1)] = (int(m.group(2)), tuple(int(m.group(3)[i:i + 2], 16) for i in (0, 2, 4)))
        elif m := REG_RE.match(line):
            regs[m.group(1)] = int(m.group(2))
        elif m := re.match(r"^(\d+) tiles definis", line):
            total = int(m.group(1))
    return colors, pals, tiles, regs, errors, total


def nearest_low(colors, rgb):
    """Couleur 0-7 la plus proche en RGB (nom, index)."""
    best = min(((sum((a - b) ** 2 for a, b in zip(rgb, c[1])), name, c[0])
                for name, c in colors.items() if c[0] < 8))
    return best[1], best[2]


def uses_mc11(rows):
    return any((r >> s) & 3 == 3 for r in rows for s in (0, 2, 4, 6))


def build(spec):
    colors, pals, tiles, regs, errors, total = parse(spec)
    warnings = []
    seen_codes, seen_names = {}, {}
    for code, name, pal, rows, n in tiles:
        if code in seen_codes:
            errors.append("ligne %d : code $%02X déjà défini ligne %d" % (n, code, seen_codes[code]))
        if name in seen_names:
            errors.append("ligne %d : nom %s déjà défini ligne %d" % (n, name, seen_names[name]))
        if pal not in pals:
            errors.append("ligne %d : palette %s inconnue" % (n, pal))
        seen_codes[code], seen_names[name] = n, n
    if total is not None and total != len(tiles):
        errors.append("%d tiles annoncés, %d trouvés" % (total, len(tiles)))
    for k, v in pals.items():
        for c in v[1].values():
            if c not in colors:
                errors.append("palette %s : couleur %s inconnue" % (k, c))
    if errors:
        return None, errors, warnings

    bg, mc1, mc2 = regs.get("D021"), regs.get("D022"), regs.get("D023")
    default = {}
    for code, name, pal, rows, n in tiles:
        mode, p = pals[pal]
        if mode == "STD":
            fixed, key = {"0": bg}, "1"
        else:
            fixed, key = {"00": bg, "01": mc1, "10": mc2}, "11"
        for k, reg in fixed.items():
            if k in p and colors[p[k]][0] != reg:
                warnings.append("%s : palette %s, %s=%s mais le registre global vaut %d"
                                % (name, pal, k, p[k], reg))
        cname = p[key]
        idx, rgb = colors[cname]
        if idx > 7:
            if mode == "MC" and not uses_mc11(rows):
                warnings.append("$%02X %s : palette %s, 11=%s (couleur %d) impossible en Color RAM, "
                                "mais le tile n'a aucun pixel 11 : sans effet" % (code, name, pal, cname, idx))
                idx = 0
            else:
                sub, sidx = nearest_low(colors, rgb)
                warnings.append("$%02X %s : palette %s, %s=%s (couleur %d) impossible en Color RAM "
                                "(0-7 seulement) : remplacée par %s (%d), la plus proche"
                                % (code, name, pal, key, cname, colors[cname][0], sub, sidx))
                idx = sidx
        default[code] = idx + (8 if mode == "MC" else 0)
    return (colors, tiles, regs, default), errors, warnings


def render(model):
    colors, tiles, regs, default = model
    first, last = min(t[0] for t in tiles), max(t[0] for t in tiles)
    by_code = {t[0]: t for t in tiles}
    s = ["; " + HEADER, ";", "; Motifs des codes $%02X-$%02X (8 octets par code, ligne 0 en haut ;" % (first, last),
         "; codes non définis : à zéro) et Color RAM par défaut de chaque code.", "",
         "        .export _tileset_glyphs, _tileset_colors", "",
         '        .segment "RODATA"', "", "_tileset_glyphs:"]
    for code in range(first, last + 1):
        t = by_code.get(code)
        rows = t[3] if t else [0] * 8
        s.append("        .byte %s   ; $%02X %s" % (",".join("$%02X" % r for r in rows), code,
                                                   ("%s %s" % (t[1], t[2])) if t else "(libre)"))
    s += ["", "_tileset_colors:"]
    for code in range(first, last + 1, 8):
        chunk = range(code, min(code + 8, last + 1))
        s.append("        .byte %s   ; $%02X-$%02X" % (",".join("$%02X" % default.get(c, 0) for c in chunk),
                                                     chunk[0], chunk[-1]))
    data_s = "\n".join(s) + "\n"

    def consts(fmt_def, comment):
        out = [comment % HEADER, "",
               comment % "Registres globaux (section 1) : fond, multicolore 1 et 2.",
               fmt_def("TILESET_BG", regs["D021"]), fmt_def("TILESET_MC1", regs["D022"]),
               fmt_def("TILESET_MC2", regs["D023"]), "",
               comment % "Couleurs de la palette (section 2).",
               *[fmt_def("TC_" + n, c[0]) for n, c in sorted(colors.items(), key=lambda kv: kv[1][0])], "",
               comment % "Codes des tiles (section 5).",
               fmt_def("TILE_FIRST", first, hexa=True), fmt_def("TILE_LAST", last, hexa=True),
               fmt_def("TILE_COUNT", len(tiles)),
               *[fmt_def("TILE_" + t[1], t[0], hexa=True) for t in sorted(tiles)]]
        return "\n".join(out) + "\n"

    h = consts(lambda n, v, hexa=False: "#define %-30s %s" % (n, ("0x%02X" % v) if hexa else v),
               "/* %s */")
    h = ("#ifndef TILES_H\n#define TILES_H\n\n" + h +
         "\n/* Motifs (TILE_FIRST..TILE_LAST) et Color RAM par défaut de chaque code. */\n"
         "extern const unsigned char tileset_glyphs[];\n"
         "extern const unsigned char tileset_colors[];\n\n#endif\n")
    inc = consts(lambda n, v, hexa=False: "%-30s = %s" % (n, ("$%02X" % v) if hexa else v), "; %s")
    inc += "\n.import _tileset_glyphs, _tileset_colors\n"
    return data_s, h, inc


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 4:
        sys.exit(__doc__.split("\n\n")[1])
    spec, outs = args[0], args[1:]
    model, errors, warnings = build(spec)
    for w in warnings:
        print("mktileset.py: ATTENTION %s" % w, file=sys.stderr)
    if errors:
        for e in errors:
            print("mktileset.py: ERREUR %s" % e, file=sys.stderr)
        return 1
    contents = render(model)
    stale = [p for p, c in zip(outs, contents)
             if not os.path.isfile(p) or open(p, encoding="utf-8").read() != c]
    if check:
        for p in stale:
            print("mktileset.py: %s n'est pas à jour (make)" % p, file=sys.stderr)
        return 1 if stale else 0
    for p, c in zip(outs, contents):
        if p in stale:
            with open(p, "w", encoding="utf-8") as f:
                f.write(c)
    print("mktileset.py: %d tiles ($%02X-$%02X), %d avertissement(s)"
          % (len(model[1]), min(t[0] for t in model[1]), max(t[0] for t in model[1]), len(warnings)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
