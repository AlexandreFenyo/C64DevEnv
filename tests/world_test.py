#!/usr/bin/env python3
"""world_test.py - vérifie libc64/world avec mygame/monde (appelé par le test 6).

Défilement fin (world_scroll) : la position (world_px, world_py) est pilotée
par les globales de mygame/monde (auto_dx/auto_dy : déplacement imposé ;
goto_req/goto_px/goto_py : saut). À l'arrêt, on lit d'un coup (émulateur
arrêté) :
- l'écran affiché ($C000 ou $C400 selon world_scroll_front, et $D018) et la
  Color RAM, lignes 0-15 : exactement la vue 40x16 de world.txt dont le coin est la case
  (px >> 3, py >> 3), recalculée ici (mêmes règles que tools/mkworld.py ;
  cases au-delà du monde : remplissage $4D, couleur 5) ;
- les registres du haut de l'écran, relus à l'entrée du handler 1 du panneau
  (ligne 174 ; plus bas, le panneau les change) : $D016 = multicolore +
  7 - (px & 7) (38 colonnes), $D011 = mode texte + 7 - (py & 7) (24 lignes ;
  le bit 7 relu est celui de la ligne raster : ignoré), $D021 = 13 ;
- la Color RAM du panneau (lignes 16-23) reste à sa couleur (blanc).
Déplacements en ligne droite et en diagonale, à 1 et 2 pixels par image :
aucune attente (vue suivante toujours prête à temps) ; blocage aux quatre
bords (chocs comptés) ; vues autour des frontières de segments.
VICE doit tourner avec build/monde.prg et le moniteur (run.sh --monitor).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dbg  # noqa: E402
import mkworld  # noqa: E402

FILL_CODE, FILL_COLOR = 0x4D, 5
ROWS, VIEW_H = 16, 121                     # WORLD_SCROLL_ROWS, WORLD_SCROLL_VIEW_H
VIEW = ROWS * 40


def fail(msg):
    print("ECHEC : " + msg)
    sys.exit(1)


class C64:
    def __init__(self):
        self.labels = dbg.Labels(os.path.join(ROOT, "build", "monde.labels"))

    def addr(self, name):
        a = self.labels.lookup(name)
        if a is None:
            fail("label %s absent de build/monde.labels" % name)
        return a

    def snapshot(self, names, top=False):
        """{nom: octets} des variables (nom, taille) et de la vue, émulateur arrêté ;
        top : arrêt à l'entrée du handler 1 du panneau (ligne 174), quand les
        registres du VIC-II sont ceux du haut de l'écran."""
        m = dbg.Monitor(6502, 10)
        try:
            if top:
                cp = m.checkpoint_set(self.addr("panel_split1"), self.addr("panel_split1"), 4)
                m.exit_monitor()
                if m.wait_stopped(5) is None:
                    fail("handler du panneau jamais atteint")
                m.checkpoint_delete(cp["num"])
            out = {n: m.mem_get(self.addr(n), self.addr(n) + k - 1) for n, k in names}
            io = m.bank_id("io")
            front = m.mem_get(self.addr("_world_scroll_front"), self.addr("_world_scroll_front"))[0]
            base = 0xC400 if front else 0xC000
            out["codes"] = m.mem_get(base, base + VIEW - 1)
            out["colors"] = bytes(b & 0x0F for b in m.mem_get(0xD800, 0xD800 + VIEW - 1, io))
            out["vic"] = m.mem_get(0xD011, 0xD021, io)
            out["panel_colors"] = bytes(b & 0x0F for b in m.mem_get(0xD800 + VIEW, 0xD800 + VIEW + 319, io))
            out["front"] = front
        finally:
            m.exit_monitor()
            m.close()
        return out

    def poke(self, name, data):
        m = dbg.Monitor(6502, 10)
        try:
            m.mem_set(self.addr(name), bytes(data))
        finally:
            m.exit_monitor()
            m.close()

    def word(self, name):
        d = self.snapshot([(name, 2)])[name]
        return d[0] | d[1] << 8

    def frames(self):
        return self.word("_world_scroll_frames")

    def wait_frames(self, n):
        f0 = self.frames()
        deadline = time.time() + 20
        while (self.frames() - f0) & 0xFFFF < n:
            if time.time() > deadline:
                fail("le handler du défilement ne tourne pas")
            time.sleep(0.05)

    def goto(self, px, py):
        self.poke("_goto_px", [px & 0xFF, px >> 8, py & 0xFF, py >> 8])
        self.poke("_goto_req", [1])
        deadline = time.time() + 10
        while self.snapshot([("_goto_req", 1)])["_goto_req"][0]:
            if time.time() > deadline:
                fail("goto non pris en compte")
            time.sleep(0.05)
        self.wait_frames(3)

    def move(self, dx, dy, frames):
        """Déplacement imposé pendant `frames` images, puis arrêt. Renvoie le
        nombre d'attentes et de chocs pendant le déplacement."""
        s0 = self.snapshot([("_world_scroll_stalls", 2), ("_world_scroll_bumps", 1)])
        self.poke("_auto_dx", [dx & 0xFF, dy & 0xFF])
        self.wait_frames(frames)
        self.poke("_auto_dx", [0, 0])
        self.wait_frames(3)
        s1 = self.snapshot([("_world_scroll_stalls", 2), ("_world_scroll_bumps", 1)])
        w = lambda d: d[0] | d[1] << 8  # noqa: E731
        return ((w(s1["_world_scroll_stalls"]) - w(s0["_world_scroll_stalls"])) & 0xFFFF,
                (s1["_world_scroll_bumps"][0] - s0["_world_scroll_bumps"][0]) & 0xFF)


def expected_view(model, rows, tx, ty):
    codes, colors = [], []
    for y in range(ty, ty + ROWS):
        for x in range(tx, tx + 40):
            if x < model["w"] and y < model["h"]:
                v = rows[y][x]
                codes.append(model["codes"][v])
                colors.append(model["colors"][v])
            else:
                codes.append(FILL_CODE)
                colors.append(FILL_COLOR)
    return bytes(codes), bytes(colors)


def check_view(c64, model, rows, what):
    s = c64.snapshot([("_world_px", 4)], top=True)
    p = s["_world_px"]
    px, py = p[0] | p[1] << 8, p[2] | p[3] << 8
    tx, ty = px >> 3, py >> 3
    ecodes, ecolors = expected_view(model, rows, tx, ty)
    if s["codes"] != ecodes:
        i = next(i for i in range(VIEW) if s["codes"][i] != ecodes[i])
        fail("%s : écran différent du monde en (%d, %d) px, case %d,%d : $%02X au lieu de $%02X"
             % (what, px, py, i % 40, i // 40, s["codes"][i], ecodes[i]))
    if s["colors"] != ecolors:
        i = next(i for i in range(VIEW) if s["colors"][i] != ecolors[i])
        fail("%s : Color RAM différente en (%d, %d) px, case %d,%d : %d au lieu de %d"
             % (what, px, py, i % 40, i // 40, s["colors"][i], ecolors[i]))
    d011, d016, d018, d021 = s["vic"][0], s["vic"][5], s["vic"][7], s["vic"][16]
    if (d016 & 0x1F) != 0x10 | (7 - (px & 7)) or (d011 & 0x7F) != 0x10 | (7 - (py & 7)) or d021 & 15 != 13:
        fail("%s : registres du haut de l'écran $D016=$%02X $D011=$%02X $D021=$%02X pour (%d, %d)"
             % (what, d016, d011, d021, px, py))
    if s["panel_colors"] != bytes([1]) * (8 * 40):
        fail("%s : Color RAM du panneau modifiée" % what)
    if d018 & 0xFE != (0x12 if s["front"] else 0x02):
        fail("%s : $D018=$%02X mais écran affiché %d" % (what, d018, s["front"]))
    print("ok : %s, (%d, %d) px : vue identique au monde (codes, Color RAM, décalage fin)" % (what, px, py))
    return px, py


def main():
    model = mkworld.build(os.path.join(ROOT, "libc64", "world", "world.txt"),
                          os.path.join(ROOT, "libc64", "tileset", "tileset.txt"))
    _, _, _, rows = mkworld.read_world(os.path.join(ROOT, "libc64", "world", "world.txt"))
    max_px, max_py = model["w"] * 8 - 304, model["h"] * 8 - VIEW_H
    c64 = C64()
    c64.wait_frames(5)
    px, py = check_view(c64, model, rows, "départ")
    if (px, py) != (max_px // 2, max_py // 2):
        fail("départ attendu au centre du monde, position (%d, %d)" % (px, py))

    # Lignes droites et diagonales, 1 et 2 pixels par image, en partant sur
    # chaque axe à 8 pixels de la case suivante (le premier franchissement
    # laisse le temps de préparer la vue ; un départ à 1 pixel d'une case
    # attend 2 ou 3 images) : aucune attente ensuite.
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1),
                   (2, 0), (-2, 0), (0, 2), (0, -2), (2, 2), (-2, -2), (2, -1)):
        x0 = (max_px // 2) // 8 * 8 + (7 if dx < 0 else 0)
        y0 = (max_py // 2) // 8 * 8 + (7 if dy < 0 else 0)
        c64.goto(x0, y0)
        stalls, bumps = c64.move(dx, dy, 100)
        if stalls or bumps:
            fail("déplacement (%+d, %+d) : %d attente(s), %d choc(s)" % (dx, dy, stalls, bumps))
        x, y = check_view(c64, model, rows, "déplacement (%+d, %+d), sans attente" % (dx, dy))
        # Au moins 100 images de déplacement (plus en --warp : le test réagit
        # moins vite que l'émulateur), dans le bon sens, axe immobile inchangé.
        mx, my = x - x0, y - y0
        for m, d in ((mx, dx), (my, dy)):
            if (d == 0 and m != 0) or (d != 0 and (m * d < 0 or abs(m) < 100 * abs(d) - 8)):
                fail("déplacement (%+d, %+d) : déplacé de (%+d, %+d) pixels" % (dx, dy, mx, my))

    # Bords : on s'approche puis on pousse.
    for what, start, d, target in (("bord droit", (max_px - 30, 300), (2, 0), lambda x, y: x == max_px),
                                   ("bord bas", (500, max_py - 30), (0, 2), lambda x, y: y == max_py),
                                   ("coin haut gauche", (20, 20), (-2, -2), lambda x, y: (x, y) == (0, 0)),
                                   ("coin bas droit", (max_px - 9, max_py - 9), (1, 1),
                                    lambda x, y: (x, y) == (max_px, max_py))):
        c64.goto(*start)
        _, bumps = c64.move(d[0], d[1], 50)
        x, y = check_view(c64, model, rows, what)
        if not target(x, y) or bumps < 5:
            fail("%s : position (%d, %d), %d choc(s)" % (what, x, y, bumps))
        print("ok : bloqué au %s (%d chocs)" % (what, bumps))

    # Vues autour des frontières de segments (40 colonnes) : nouvelles colonnes
    # à droite et à gauche, nouvelles lignes en haut et en bas.
    for x, y, dx, dy in ((38 * 8, 56, 1, 0), (41 * 8, 300, -1, 0), (78 * 8 + 3, 800, 0, 1), (119 * 8, 9, 1, 1),
                         (158 * 8 + 7, 990, -1, -1), (239 * 8, 400, 2, 0), (318 * 8 + 1, 616, -2, 1),
                         (358 * 8, 100, 1, -1)):
        c64.goto(x, y)
        c64.move(dx, dy, 20)
        check_view(c64, model, rows, "frontières de segments")
    print("monde OK")


if __name__ == "__main__":
    main()
