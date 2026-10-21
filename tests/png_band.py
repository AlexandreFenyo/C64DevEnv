#!/usr/bin/env python3
"""png_band.py CAPTURE.png [COULEUR] - bords d'une bande de couleur sur une
capture de dbg.py (PNG indexé 384x272, zone affichée x=32..351).

Affiche « haut=<rangs> bas=<rangs> n=<hauteur à x=100> » : pour chaque bord, la
liste des rangs (y) distincts sur la largeur affichée, dans l'ordre des x ;
un seul rang = bord rectiligne. Rang de capture = ligne raster - 15.
"""
import struct
import sys
import zlib


def rows_of(path):
    d = open(path, "rb").read()
    pos, idat, w = 8, b"", 0
    while pos < len(d):
        n = struct.unpack(">I", d[pos:pos + 4])[0]
        t, body = d[pos + 4:pos + 8], d[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            w = struct.unpack(">I", body[:4])[0]
        elif t == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    return [raw[y * (w + 1) + 1:(y + 1) * (w + 1)] for y in range(len(raw) // (w + 1))]


def main():
    rows = rows_of(sys.argv[1])
    color = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    tops, bots = [], []
    for x in range(32, 352):
        ys = [y for y, r in enumerate(rows) if r[x] == color]
        for lst, v in ((tops, ys[0] if ys else -1), (bots, ys[-1] if ys else -1)):
            if not lst or lst[-1] != v:
                lst.append(v)
    n = sum(1 for r in rows if r[100] == color)
    print("haut=%s bas=%s n=%d" % (",".join(map(str, tops)), ",".join(map(str, bots)), n))


if __name__ == "__main__":
    main()
