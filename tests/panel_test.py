#!/usr/bin/env python3
"""panel_test.py - vérifie la coupure de l'écran entre la vue qui défile
(world_scroll) et le panneau (libc64/panel) avec mygame/monde (test 6).

Pour les 8 valeurs du décalage vertical (py & 7) et une de plus, vue
immobile, capture de l'écran (rang de capture = ligne raster - 16) :
- lignes raster 176-183 : entièrement noires (bande de séparation) ;
- panneau (lignes 184-246) : identique au pixel près pour tous les décalages
  (sauf la ligne de texte de la position), et le texte de mygame/monde y est
  (écran $F000, ligne PANEL_ROW) ;
- motifs du panneau : seuls A-Z, chiffres, espace, « : », « = » copiés de la
  ROM ; codes libres à zéro, sauf le graphique de mygame/monde (code 128) ;
- vue (lignes 55-175) : en descendant d'un pixel dans le monde, l'image
  remonte d'une ligne : lignes 56-175 en py = lignes 55-174 en py + 1 ; la
  dernière ligne de la vue (175) est donc complète, jusqu'au bord droit.
VICE doit tourner avec build/monde.prg et le moniteur (run.sh --monitor).
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import dbg  # noqa: E402
from png_band import rows_of  # noqa: E402

CAP = os.path.join(ROOT, "build", "panel_test.png")
OFF = 16                                  # rang de capture = ligne raster - OFF (mesuré)


def fail(msg):
    print("ECHEC : " + msg)
    sys.exit(1)


def main():
    labels = dbg.Labels(os.path.join(ROOT, "build", "monde.labels"))

    def poke(name, data):
        m = dbg.Monitor(6502, 10)
        try:
            m.mem_set(labels.lookup(name), bytes(data))
        finally:
            m.exit_monitor()
            m.close()

    def shot(px, py):
        poke("_goto_px", [px & 0xFF, px >> 8, py & 0xFF, py >> 8])
        poke("_goto_req", [1])
        time.sleep(0.5)
        subprocess.run([os.path.join(ROOT, "tools", "dbg.py"), "capture", CAP], check=True,
                       stdout=subprocess.DEVNULL)
        return rows_of(CAP)

    # Motifs du panneau ($E000-$E7FF) : caractères du texte copiés de la ROM
    # (jeu majuscules, $D000), codes libres à zéro sauf la boussole de
    # mygame/monde (code 128, panel_glyph) ; texte en codes écran du jeu
    # majuscules ; boussole posée en (1, 0), en jaune.
    text_codes = set(range(1, 27)) | {32, 61} | set(range(48, 59))
    compass = bytes([0x18, 0x3C, 0x5A, 0xFF, 0x5A, 0x18, 0x18, 0x00])
    m = dbg.Monitor(6502, 10)
    try:
        ram, rom, io = m.bank_id("ram"), m.bank_id("rom"), m.bank_id("io")
        text = m.mem_get(0xF000 + 16 * 40, 0xF000 + 16 * 40 + 39, ram)
        charset = m.mem_get(0xE000, 0xE7FF, ram)
        chargen = m.mem_get(0xD000, 0xD7FF, rom)
        color = m.mem_get(0xD800 + 16 * 40, 0xD800 + 16 * 40 + 1, io)
    finally:
        m.exit_monitor()
        m.close()
    if text[1] != 128 or text[3:8] != bytes([13, 15, 14, 4, 5]):           # boussole, « MONDE »
        fail("panneau : texte absent de l'écran $F000 (%s)" % text[:16].hex())
    for code in range(256):
        glyph = charset[code * 8:code * 8 + 8]
        if code in text_codes:
            expected = chargen[code * 8:code * 8 + 8]
        elif code == 128:
            expected = compass
        else:
            expected = bytes(8)
        if glyph != expected:
            fail("motif du code %d : %s au lieu de %s" % (code, glyph.hex(), expected.hex()))
    if color[1] & 15 != 7 or color[0] & 15 != 1:
        fail("panneau : couleurs %s (blanc, puis jaune pour la boussole)" % color.hex())
    print("ok : motifs du panneau : %d caractères de la ROM, codes libres à zéro, boussole (code 128)"
          % len(text_codes))

    px, base = 1000, 504
    shots = [shot(px, base + k) for k in range(9)]
    panel = None
    for k, rows in enumerate(shots):
        y = 7 - ((base + k) & 7)
        for line in range(176, 184):
            if any(rows[line - OFF]):
                fail("y=%d : ligne %d de la bande pas entièrement noire" % (y, line))
        # Panneau, sauf sa ligne 6 (raster 232-239) : la position affichée par
        # mygame/monde change quand py passe à la case suivante.
        p = rows[184 - OFF:232 - OFF] + rows[240 - OFF:247 - OFF]
        if panel is None:
            panel = p
            if not any(any(r) for r in p):
                fail("panneau vide à l'écran")
        elif p != panel:
            i = next(i for i in range(len(p)) if p[i] != panel[i])
            line = 184 + i if i < 48 else 192 + i
            fail("y=%d : panneau différent à la ligne %d" % (y, line))
        if k:
            prev = shots[k - 1]
            for line in range(55, 175):
                if rows[line - OFF] != prev[line + 1 - OFF]:
                    fail("y=%d : vue discontinue, ligne %d (py=%d) au lieu de la ligne %d (py=%d)"
                         % (y, line, base + k, line + 1, base + k - 1))
        print("ok : décalage vertical %d : bande noire 176-183, panneau intact, vue continue" % y)
    print("panneau OK")


if __name__ == "__main__":
    main()
