#!/usr/bin/env python3
"""mkworld.py - compresse le monde (libc64/world/world.txt) pour libc64/world.

Usage : mkworld.py [--check] WORLD.txt TILESET.txt DATA.s WORLD.h WORLD_DEFS.inc

Une case = un octet : index dans la table des valeurs de case (code de tile +
Color RAM finale ; NV valeurs, NV <= 250). Chaque ligne du monde est codée :
  octet < NV      : littéral, la case vaut cet index ;
  octet >= NV     : répétition de la case précédente (octet - NV + 2) fois.
Les lignes sont coupées tous les WORLD_SEG (20) colonnes : chaque segment
commence par un littéral, et une table donne l'adresse de chaque segment
(20 tables de WORLD_H octets bas + 20 d'octets hauts, une par numéro de
segment). Lire une case = partir du segment qui la contient et décoder au
plus 19 cases avant ; une ligne de 40 cases enchaîne 2 ou 3 segments.

Ces octets (« jetons ») sont ensuite codés en quartets, poids fort d'abord
(décodeur : libc64/include/world_nib.inc) : quartet 0-14 = l'un des 15
jetons les plus fréquents (table world_nib_top), quartet 15 = échappement,
jeton dans les deux quartets suivants. Chaque segment commence sur un octet
entier (accès direct par la table) ; les segments codés identiques ne sont
stockés qu'une fois (plusieurs entrées de la table pointent dessus).

Color RAM finale d'une valeur : celle du tile (tileset.txt) si la carte n'en
impose pas ; sinon la couleur imposée, + 8 si le tile est multicolore.
Vérification : tout le monde est redécodé et comparé avant d'écrire.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mktileset  # noqa: E402

SEG = 20                # 20 plutôt que 40 : saut de 19 cases au plus pour 658 octets de plus (mesuré)
HEADER = "Généré par tools/mkworld.py depuis libc64/world/world.txt : ne pas modifier."


def read_world(path):
    w = h = None
    values, rows = {}, []
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if not p or p[0].startswith("#"):
            continue
        if p[0] == "W":
            w = int(p[1])
        elif p[0] == "H":
            h = int(p[1])
        elif p[0] == "C":
            values[int(p[1], 16)] = (int(p[2], 16), None if p[3] == "-" else int(p[3]))
        elif p[0] == "R":
            row = bytes.fromhex(p[2])
            if len(row) != w:
                raise ValueError("ligne %s : %d cases au lieu de %d" % (p[1], len(row), w))
            rows.append(row)
    if len(rows) != h:
        raise ValueError("%d lignes au lieu de %d" % (len(rows), h))
    if sorted(values) != list(range(len(values))):
        raise ValueError("index de valeurs non contigus")
    return w, h, [values[i] for i in range(len(values))], rows


def encode_row(row, nv):
    """Liste des segments (octets) de la ligne."""
    maxrep = 255 - nv + 2
    segs = []
    for s in range(0, len(row), SEG):
        part, out, x = row[s:s + SEG], [], 0
        while x < len(part):
            v, n = part[x], 1
            while x + n < len(part) and part[x + n] == v:
                n += 1
            out.append(v)
            rem = n - 1
            while rem >= 2:
                k = min(rem, maxrep)
                out.append(nv + k - 2)
                rem -= k
            if rem == 1:
                out.append(v)
            x += n
        segs.append(bytes(out))
    return segs


def nib_encode(tokens, top):
    """Jetons -> octets (quartets, poids fort d'abord, dernier complété par 0)."""
    nibs = []
    for t in tokens:
        if t in top:
            nibs.append(top.index(t))
        else:
            nibs += [15, t >> 4, t & 15]
    if len(nibs) & 1:
        nibs.append(0)
    return bytes(nibs[i] << 4 | nibs[i + 1] for i in range(0, len(nibs), 2))


def skip_tables(top, nv):
    """Tables du saut rapide par octet (voir render)."""
    cells = lambda t: 1 if t < nv else t - nv + 2  # noqa: E731
    cells2, lastlit = [], []
    for b in range(256):
        hi, lo = b >> 4, b & 15
        if hi == 15 or lo == 15:
            cells2.append(0)
            lastlit.append(0xFF)
            continue
        cells2.append(cells(top[hi]) + cells(top[lo]))
        lastlit.append(top[lo] if top[lo] < nv else top[hi] if top[hi] < nv else 0xFF)
    return cells2, lastlit


def decode(data, start, count, nv, top):
    """Comme le décodeur 6502 : quartets puis littéraux/répétitions."""
    pos, half = start, False

    def nib():
        nonlocal pos, half
        if half:
            half = False
            return data[pos - 1] & 15
        half = True
        pos += 1
        return data[pos - 1] >> 4

    def token():
        n = nib()
        if n < 15:
            return top[n]
        return nib() << 4 | nib()

    out, val, rep = [], None, 0
    while len(out) < count:
        if rep:
            rep -= 1
        else:
            b = token()
            if b < nv:
                val = b
            else:
                rep = b - nv + 1
        out.append(val)
    return out


def build(world_path, tileset_path):
    w, h, values, rows = read_world(world_path)
    nv = len(values)
    if nv > 250:
        raise ValueError("%d valeurs de case : 250 au plus (il faut des octets libres pour les répétitions)" % nv)
    model, errors, _ = mktileset.build(tileset_path)
    if errors:
        raise ValueError("tileset : " + "; ".join(errors))
    default = model[3]
    codes, colors = [], []
    for code, color in values:
        if code not in default:
            raise ValueError("tile $%02X absent du tileset" % code)
        d = default[code]
        codes.append(code)
        colors.append(d if color is None else color + (8 if d >= 8 else 0))
    segs = [encode_row(row, nv) for row in rows]
    freq = {}
    for t in set(s for r in segs for s in r):        # fréquences sur les segments distincts
        for b in t:
            freq[b] = freq.get(b, 0) + 1
    top = sorted(freq, key=lambda b: (-freq[b], b))[:15]
    data, entries, where = bytearray(), [], {}       # entries[y][k] = décalage
    tokens = 0
    for r in segs:
        offs = []
        for seg in r:
            enc = nib_encode(seg, top)
            if enc not in where:
                where[enc] = len(data)
                data += enc
                tokens += len(seg)
            offs.append(where[enc])
        entries.append(offs)
    nseg = len(entries[0])
    for y, row in enumerate(rows):       # vérification complète
        for k in range(nseg):
            n = min(SEG, w - k * SEG)
            if decode(data, entries[y][k], n, nv, top) != list(row[k * SEG:k * SEG + n]):
                raise ValueError("décodage incorrect ligne %d segment %d" % (y, k))
    return dict(w=w, h=h, nv=nv, nseg=nseg, codes=codes, colors=colors, data=bytes(data), entries=entries,
                top=top, distinct=len(where), tokens=tokens)


def render(m):
    s = ["; " + HEADER, ";",
         "; Monde %dx%d tiles : %d valeurs de case, %d segments de %d colonnes par ligne"
         % (m["w"], m["h"], m["nv"], m["nseg"], SEG),
         "; (%d distincts : %d jetons, %d octets en quartets)." % (m["distinct"], m["tokens"], len(m["data"])),
         "", '        .include "world_defs.inc"', "",
         "        .export _world_cell_code, _world_cell_color, _world_seg_lo, _world_seg_hi",
         "        .export world_seglo_lo, world_seglo_hi, world_seghi_lo, world_seghi_hi, world_nib_top",
         "        .export world_nib_cells2, world_nib_lastlit",
         "", '        .segment "RODATA"', "",
         "; Valeur de case -> code de tile, Color RAM finale."]
    for name, tab in (("_world_cell_code", m["codes"]), ("_world_cell_color", m["colors"])):
        s.append(name + ":")
        for i in range(0, len(tab), 16):
            s.append("        .byte " + ",".join("$%02X" % v for v in tab[i:i + 16]))
    s += ["", "; Les 15 jetons codés par un seul quartet (0-14).",
          "world_nib_top: .byte " + ",".join("$%02X" % b for b in m["top"])]
    cells2, lastlit = skip_tables(m["top"], m["nv"])
    s += ["", "; Saut rapide (world_render_col) : pour un octet de 2 quartets sans",
          "; échappement, nombre de cases de ses 2 jetons (0 : échappement), et",
          "; dernier littéral (valeur de case) qu'il contient ($FF : aucun)."]
    for name, tab in (("world_nib_cells2", cells2), ("world_nib_lastlit", lastlit)):
        s.append(name + ":")
        for i in range(0, 256, 16):
            s.append("        .byte " + ",".join("$%02X" % v for v in tab[i:i + 16]))
    s += ["", "; Adresse du segment k de la ligne y : _world_seg_lo/hi + k * WORLD_H + y."]
    for name, sel in (("_world_seg_lo", "<"), ("_world_seg_hi", ">")):
        s.append(name + ":")
        for k in range(m["nseg"]):
            vals = ["%s(rows+%d)" % (sel, m["entries"][y][k]) for y in range(m["h"])]
            for i in range(0, len(vals), 10):
                s.append("        .byte " + ",".join(vals[i:i + 10]))
    s += ["", "; Début de la table du segment k (octets bas puis octets hauts)."]
    for name, base, sel in (("world_seglo_lo", "_world_seg_lo", "<"), ("world_seglo_hi", "_world_seg_lo", ">"),
                            ("world_seghi_lo", "_world_seg_hi", "<"), ("world_seghi_hi", "_world_seg_hi", ">")):
        s.append("%s: .byte %s" % (name, ",".join("%s(%s+%d)" % (sel, base, k * m["h"]) for k in range(m["nseg"]))))
    s += ["", "; Lignes codées.", "rows:"]
    d = m["data"]
    for i in range(0, len(d), 32):
        s.append("        .byte " + ",".join("$%02X" % b for b in d[i:i + 32]))
    data_s = "\n".join(s) + "\n"

    consts = [("WORLD_W", m["w"]), ("WORLD_H", m["h"]), ("WORLD_VIEW_W", 40), ("WORLD_VIEW_H", 25),
              ("WORLD_MAX_X", m["w"] - 40), ("WORLD_MAX_Y", m["h"] - 25), ("WORLD_SEG", SEG),
              ("WORLD_NSEG", m["nseg"]), ("WORLD_NV", m["nv"])]
    inc = "; %s\n\n" % HEADER + "".join("%-14s = %d\n" % c for c in consts)
    h = ("/* %s */\n#ifndef LIBC64_WORLD_H\n#define LIBC64_WORLD_H\n\n" % HEADER
         + "".join("#define %-14s %d\n" % c for c in consts) + "\n#endif\n")
    return data_s, h, inc


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 5:
        sys.exit(__doc__.split("\n\n")[1])
    try:
        m = build(args[0], args[1])
    except (ValueError, OSError) as e:
        print("mkworld.py: ERREUR %s" % e, file=sys.stderr)
        return 1
    contents = render(m)
    outs = args[2:]
    stale = [p for p, c in zip(outs, contents)
             if not os.path.isfile(p) or open(p, encoding="utf-8").read() != c]
    if check:
        for p in stale:
            print("mkworld.py: %s n'est pas à jour (make)" % p, file=sys.stderr)
        return 1 if stale else 0
    for p, c in zip(outs, contents):
        if p in stale:
            with open(p, "w", encoding="utf-8") as f:
                f.write(c)
    print("mkworld.py: monde %dx%d, %d valeurs, %d segments distincts, %d octets codés (quartets) + %d de tables (vérifié)"
          % (m["w"], m["h"], m["nv"], m["distinct"], len(m["data"]),
             2 * m["h"] * m["nseg"] + 2 * m["nv"] + 4 * m["nseg"] + len(m["top"]) + 512))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
