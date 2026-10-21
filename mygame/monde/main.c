/* mygame/monde - promenade dans le monde du jeu (libc64/world) : la vue de
   40x25 tiles se déplace d'une case à la fois, à la manette (port 2) ou au
   clavier (flèches, ou W A S D), et s'arrête sur les bords du monde (la
   bordure clignote en rouge quand on bute). Défilement par case (pas encore
   au pixel) : chaque pas redessine la vue (~3 images). */
#include <c64.h>
#include <cbm.h>
#include "libc64.h"
#include "tiles.h"
#include "world.h"

#define START_X ((WORLD_W - WORLD_VIEW_W) / 2)    /* départ au centre du monde */
#define START_Y ((WORLD_H - WORLD_VIEW_H) / 2)
#define BUMP_FRAMES 6                              /* durée du clignotement sur un bord */

/* Globales : lues par le débogueur et par le test 6. */
unsigned int cam_x = START_X;       /* case du coin haut gauche de la vue */
unsigned char cam_y = START_Y;
unsigned int redraws;               /* nombre de vues dessinées */
unsigned char bumps;                /* nombre de fois où l'on a buté sur un bord */

int main(void)
{
    unsigned char joy, key, bump = 0;
    signed char dx, dy;

    tileset_install();
    VIC.bordercolor = COLOR_BLACK;
    world_draw(cam_x, cam_y);
    ++redraws;

    for (;;) {
        wait_frame();
        if (bump && --bump == 0) {
            VIC.bordercolor = COLOR_BLACK;
        }
        dx = dy = 0;
        joy = joy2_read();
        key = cbm_k_getin();                        /* 0 si aucune touche */
        if ((joy & J_LEFT) || key == CH_CURS_LEFT || key == 'a') dx = -1;
        if ((joy & J_RIGHT) || key == CH_CURS_RIGHT || key == 'd') dx = 1;
        if ((joy & J_UP) || key == CH_CURS_UP || key == 'w') dy = -1;
        if ((joy & J_DOWN) || key == CH_CURS_DOWN || key == 's') dy = 1;
        if (dx == 0 && dy == 0) {
            continue;
        }
        /* Bords : on n'avance que si la vue reste dans le monde. */
        if ((dx < 0 && cam_x == 0) || (dx > 0 && cam_x == WORLD_MAX_X)
            || (dy < 0 && cam_y == 0) || (dy > 0 && cam_y == WORLD_MAX_Y)) {
            ++bumps;
            bump = BUMP_FRAMES;
            VIC.bordercolor = COLOR_RED;
        }
        if (dx < 0 && cam_x > 0) --cam_x;
        if (dx > 0 && cam_x < WORLD_MAX_X) ++cam_x;
        if (dy < 0 && cam_y > 0) --cam_y;
        if (dy > 0 && cam_y < WORLD_MAX_Y) ++cam_y;
        world_draw(cam_x, cam_y);
        ++redraws;
    }
    return 0;
}
