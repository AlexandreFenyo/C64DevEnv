#!/usr/bin/env python3
"""world_test.py - vérifie libc64/world avec mygame/monde (appelé par le test 6).

- La vue affichée (écran $C000 + Color RAM) est exactement la fenêtre 40x25 de
  world.txt à la position de la caméra (cam_x, cam_y), recalculée ici en Python
  (codes de tile et Color RAM, mêmes règles que tools/mkworld.py) ;
- touches flèches envoyées au clavier du C64 : la caméra avance d'une case par
  touche et s'arrête aux bords du monde (bumps compte les chocs) ;
- vérifié au départ, au bord droit, puis au coin haut gauche.
VICE doit tourner avec build/monde.prg et le moniteur (run.sh --monitor).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dbg  # noqa: E402
import mkworld  # noqa: E402

RIGHT, LEFT, DOWN, UP = 0x1D, 0x9D, 0x11, 0x91        # PETSCII des flèches


def fail(msg):
    print("ECHEC : " + msg)
    sys.exit(1)


def expected_view(model, rows, cx, cy):
    codes, colors = [], []
    for y in range(cy, cy + 25):
        for x in range(cx, cx + 40):
            v = rows[y][x]
            codes.append(model["codes"][v])
            colors.append(model["colors"][v])
    return bytes(codes), bytes(colors)


class C64:
    def __init__(self):
        self.labels = dbg.Labels(os.path.join(ROOT, "build", "monde.labels"))

    def mon(self):
        return dbg.Monitor(6502, 10)

    def read(self, name, n):
        m = self.mon()
        try:
            st = m.status()["stopped"]
            data = m.mem_get(self.labels.lookup(name), self.labels.lookup(name) + n - 1)
            return data
        finally:
            if not st:
                m.exit_monitor()
            m.close()

    def cam(self):
        d = self.read("_cam_x", 3)
        return d[0] | (d[1] << 8), d[2]

    def screen(self):
        m = self.mon()
        try:
            codes = m.mem_get(0xC000, 0xC000 + 999)
            colors = bytes(b & 0x0F for b in m.mem_get(0xD800, 0xD800 + 999, m.bank_id("io")))
        finally:
            m.exit_monitor()
            m.close()
        return codes, colors

    def poke(self, name, data):
        m = self.mon()
        try:
            m.mem_set(self.labels.lookup(name), bytes(data))
        finally:
            m.exit_monitor()
            m.close()

    def keys(self, key, count):
        """count appuis, par paquets de 8 (tampon clavier du KERNAL : 10), en
        attendant que chaque paquet soit consommé et les vues redessinées."""
        while count > 0:
            n = min(8, count)
            before = self.read("_redraws", 2)
            m = self.mon()
            try:
                m.keyboard_feed(bytes([key]) * n)
            finally:
                m.exit_monitor()
                m.close()
            deadline = time.time() + 20
            while time.time() < deadline:
                time.sleep(0.05)
                if self.read("_redraws", 2) != before and self._kbuf_empty():
                    break
            else:
                fail("touches non consommées")
            time.sleep(0.2)
            count -= n

    def _kbuf_empty(self):
        m = self.mon()
        try:
            return m.mem_get(0xC6, 0xC6)[0] == 0
        finally:
            m.exit_monitor()
            m.close()


def check_view(c64, model, rows, what):
    time.sleep(0.3)
    cx, cy = c64.cam()
    codes, colors = c64.screen()
    ecodes, ecolors = expected_view(model, rows, cx, cy)
    if codes != ecodes:
        i = next(i for i in range(1000) if codes[i] != ecodes[i])
        fail("%s : écran différent du monde en (%d, %d), case %d,%d : $%02X au lieu de $%02X"
             % (what, cx, cy, i % 40, i // 40, codes[i], ecodes[i]))
    if colors != ecolors:
        i = next(i for i in range(1000) if colors[i] != ecolors[i])
        fail("%s : Color RAM différente en (%d, %d), case %d,%d : %d au lieu de %d"
             % (what, cx, cy, i % 40, i // 40, colors[i], ecolors[i]))
    print("ok : %s, vue (%d, %d) identique au monde (codes et Color RAM)" % (what, cx, cy))
    return cx, cy


def main():
    model = mkworld.build(os.path.join(ROOT, "libc64", "world", "world.txt"),
                          os.path.join(ROOT, "libc64", "tileset", "tileset.txt"))
    _, _, _, rows = mkworld.read_world(os.path.join(ROOT, "libc64", "world", "world.txt"))
    c64 = C64()
    deadline = time.time() + 20
    while c64.read("_redraws", 2) == b"\0\0":
        if time.time() > deadline:
            fail("monde : aucune vue dessinée")
        time.sleep(0.1)
    cx, cy = check_view(c64, model, rows, "départ")
    if (cx, cy) != ((model["w"] - 40) // 2, (model["h"] - 25) // 2):
        fail("départ attendu au centre du monde, caméra en (%d, %d)" % (cx, cy))

    # Bord droit : WORLD_MAX_X - cx pas + 4 de trop.
    c64.keys(RIGHT, model["w"] - 40 - cx + 4)
    cx2, _ = check_view(c64, model, rows, "bord droit")
    bumps = c64.read("_bumps", 1)[0]
    if cx2 != model["w"] - 40 or bumps < 4:
        fail("bord droit : caméra x=%d (attendu %d), chocs %d (4 attendus)" % (cx2, model["w"] - 40, bumps))
    print("ok : bloqué au bord droit (x=%d, %d chocs)" % (cx2, bumps))

    # Coin haut gauche : on rapproche la caméra puis 3 pas de trop dans chaque sens.
    c64.poke("_cam_x", [2, 0, 2])
    c64.keys(LEFT, 5)
    c64.keys(UP, 5)
    cx3, cy3 = check_view(c64, model, rows, "coin haut gauche")
    if (cx3, cy3) != (0, 0) or c64.read("_bumps", 1)[0] < bumps + 6:
        fail("coin haut gauche : caméra (%d, %d), chocs %d" % (cx3, cy3, c64.read("_bumps", 1)[0]))
    print("ok : bloqué en (0, 0)")

    # Bas : on rapproche puis on dépasse.
    c64.poke("_cam_y", [model["h"] - 25 - 2])
    c64.keys(DOWN, 4)
    _, cy4 = check_view(c64, model, rows, "bord bas")
    if cy4 != model["h"] - 25:
        fail("bord bas : y=%d (attendu %d)" % (cy4, model["h"] - 25))
    print("ok : bloqué au bord bas (y=%d)" % cy4)

    # Balayage : colonnes autour des frontières de segments (40 cases) et
    # lignes variées ; chaque vue est demandée par un pas à droite.
    for x, y in ((38, 7), (39, 33), (78, 100), (119, 1), (158, 124), (239, 50), (318, 77), (358, 12)):
        c64.poke("_cam_x", [x & 0xFF, x >> 8, y])
        c64.keys(RIGHT, 1)
        check_view(c64, model, rows, "balayage")
    print("monde OK")


if __name__ == "__main__":
    main()
