#!/usr/bin/env python3
"""mkworld.py - compresse le monde (libc64/world/world.txt) pour libc64/world.

Usage : mkworld.py [--check] WORLD.txt TILESET.txt DATA.s WORLD.h WORLD_DEFS.inc

Une case = un octet : index dans la table des valeurs de case (code de tile +
Color RAM finale ; NV valeurs, NV <= 250). Chaque ligne du monde est codée :
  octet < NV      : littéral, la case vaut cet index ;
  octet >= NV     : répétition de la case précédente (octet - NV + 2) fois.
Les lignes sont coupées tous les WORLD_SEG (40) colonnes : chaque segment
commence par un littéral, et une table donne l'adresse de chaque segment
(10 tables de WORLD_H octets bas + 10 d'octets hauts, une par numéro de
segment). Lire une case ou une ligne de 40 cases = partir du segment
contenant la colonne et décoder au plus 39 cases avant.

Color RAM finale d'une valeur : celle du tile (tileset.txt) si la carte n'en
impose pas ; sinon la couleur imposée, + 8 si le tile est multicolore.
Vérification : tout le monde est redécodé et comparé avant d'écrire.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mktileset  # noqa: E402

SEG = 40
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


def decode(data, start, count, nv):
    out, pos, val, rep = [], start, None, 0
    while len(out) < count:
        if rep:
            rep -= 1
        else:
            b = data[pos]
            pos += 1
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
    data, entries = bytearray(), []      # entries[y][k] = décalage
    for row in rows:
        offs = []
        for seg in encode_row(row, nv):
            offs.append(len(data))
            data += seg
        entries.append(offs)
    nseg = len(entries[0])
    for y, row in enumerate(rows):       # vérification complète
        for k in range(nseg):
            n = min(SEG, w - k * SEG)
            if decode(data, entries[y][k], n, nv) != list(row[k * SEG:k * SEG + n]):
                raise ValueError("décodage incorrect ligne %d segment %d" % (y, k))
    return dict(w=w, h=h, nv=nv, nseg=nseg, codes=codes, colors=colors, data=bytes(data), entries=entries)


def render(m):
    s = ["; " + HEADER, ";",
         "; Monde %dx%d tiles : %d valeurs de case, %d octets de lignes codées, %d segments"
         % (m["w"], m["h"], m["nv"], len(m["data"]), m["nseg"]) + " de %d colonnes par ligne." % SEG,
         "", '        .include "world_defs.inc"', "",
         "        .export _world_cell_code, _world_cell_color, _world_seg_lo, _world_seg_hi",
         "        .export world_seglo_lo, world_seglo_hi, world_seghi_lo, world_seghi_hi",
         "", '        .segment "RODATA"', "",
         "; Valeur de case -> code de tile, Color RAM finale."]
    for name, tab in (("_world_cell_code", m["codes"]), ("_world_cell_color", m["colors"])):
        s.append(name + ":")
        for i in range(0, len(tab), 16):
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
    print("mkworld.py: monde %dx%d, %d valeurs, %d octets codés + %d de tables (vérifié)"
          % (m["w"], m["h"], m["nv"], len(m["data"]), 2 * m["h"] * m["nseg"] + 2 * m["nv"] + 4 * m["nseg"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
