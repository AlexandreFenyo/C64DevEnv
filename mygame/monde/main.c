/* mygame/monde - promenade dans le monde du jeu (libc64/world), avec
   défilement fin au pixel (world_scroll_*) : manette (port 2) ou clavier
   (flèches, ou W A S D, maintenues), 1 pixel par image ; bouton de tir ou
   barre d'espace : 2 pixels par image. La vue s'arrête aux bords du monde.
   Le déplacement est appliqué à chaque image par le handler raster de
   world_scroll ; la boucle principale lit les commandes et prépare la vue
   suivante (world_scroll_work).
   Mesure du temps processeur : pendant la préparation de la vue suivante
   (écran caché du double tampon), le tour de l'écran ($D020) passe au blanc :
   la hauteur des bandes blanches = part du temps de l'image occupée.
   Touche M : mesure affichée ou non. */
#include <c64.h>
#include "libc64.h"
#include "tiles.h"
#include "world.h"

#define START_PX (WORLD_SCROLL_MAX_PX / 2)    /* départ au centre du monde */
#define START_PY (WORLD_SCROLL_MAX_PY / 2)

/* Matrice du clavier lue par le KERNAL : touche enfoncée ($CB, 64 = aucune)
   et touches de modification ($028D, bit 0 = SHIFT). */
#define KEY_NOW   (*(unsigned char *)0x00CB)
#define KEY_SHIFT (*(unsigned char *)0x028D & 1)
#define K_CRSR_LR 2                            /* droite ; avec SHIFT : gauche */
#define K_CRSR_UD 7                            /* bas ; avec SHIFT : haut */
#define K_W 9
#define K_A 10
#define K_S 13
#define K_D 18
#define K_SPACE 60
#define K_M 36
#define METER_COLOR COLOR_WHITE                /* tour pendant world_scroll_work() */

/* Globales : lues par le débogueur et par le test 6. */
signed char auto_dx, auto_dy;       /* déplacement imposé (tests, démonstration) */
unsigned char goto_req;             /* 1 : aller en (goto_px, goto_py) */
unsigned int goto_px, goto_py;
unsigned char meter = 1;            /* 1 : tour blanc pendant la préparation de la vue */

int main(void)
{
    unsigned char joy, key, shift, speed, last_key = 64;
    signed char dx, dy;

    tileset_install();
    VIC.bordercolor = COLOR_BLACK;
    world_scroll_init(START_PX, START_PY);

    for (;;) {
        if (goto_req) {
            goto_req = 0;
            world_scroll_init(goto_px, goto_py);
        }
        joy = joy2_read();
        key = KEY_NOW;
        shift = KEY_SHIFT;
        dx = auto_dx;
        dy = auto_dy;
        if ((joy & J_LEFT) || key == K_A || (key == K_CRSR_LR && shift)) dx = -1;
        if ((joy & J_RIGHT) || key == K_D || (key == K_CRSR_LR && !shift)) dx = 1;
        if ((joy & J_UP) || key == K_W || (key == K_CRSR_UD && shift)) dy = -1;
        if ((joy & J_DOWN) || key == K_S || (key == K_CRSR_UD && !shift)) dy = 1;
        speed = ((joy & J_FIRE) || key == K_SPACE) ? 2 : 1;
        if (key == K_M && last_key != K_M) {        /* M : mesure affichée ou non */
            meter ^= 1;
        }
        last_key = key;
        world_scroll_dx = dx * speed;
        world_scroll_dy = dy * speed;

        world_scroll_meter = meter ? METER_COLOR : WORLD_SCROLL_NO_METER;
        world_scroll_work();
    }
    return 0;
}
