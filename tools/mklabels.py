#!/usr/bin/env python3
"""mklabels.py - normalise un fichier de labels ld65 (-Ln) en commandes "al"
pour le moniteur VICE.

ld65 -Ln produit des lignes "al 00080D .start". VICE les accepte, mais on
filtre les symboles internes sans intérêt (tailles de segments, valeurs hors
espace 16 bits) et on écrit un format fixe, trié par adresse :

    al C:080d .start

Ce fichier sert à la fois à -moncommands (VICE) et à tools/dbg.py.

Usage : mklabels.py entree.lbl sortie.labels [--keep-internal]
"""
import argparse
import re
import sys

LINE_RE = re.compile(r"^al\s+(?:C:)?([0-9A-Fa-f]+)\s+\.?(\S+)\s*$")


def convert(src, dst, keep_internal=False):
    labels = []
    with open(src, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE_RE.match(line.strip())
            if not m:
                continue
            addr = int(m.group(1), 16)
            name = m.group(2)
            if addr > 0xFFFF:
                continue
            if not keep_internal and name.startswith("__") and name.endswith("__"):
                # __CODE_SIZE__, __EXEHDR__... : bruit pour le débogage.
                continue
            labels.append((addr, name))
    labels.sort()
    with open(dst, "w", encoding="utf-8") as f:
        for addr, name in labels:
            f.write("al C:%04x .%s\n" % (addr, name))
    return len(labels)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--keep-internal", action="store_true",
                    help="conserver les symboles __XXX__ de cc65")
    args = ap.parse_args()
    try:
        n = convert(args.src, args.dst, args.keep_internal)
    except OSError as e:
        sys.exit("mklabels.py: %s" % e)
    print("mklabels.py: %d labels -> %s" % (n, args.dst))


if __name__ == "__main__":
    main()
