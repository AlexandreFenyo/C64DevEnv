/* mygame/demo - première version du jeu : un vaisseau piloté à la manette
   (port 2), un son quand on appuie sur le bouton de tir, et une bande de
   couleur de 3 lignes au milieu de l'écran, dessinée par interruption raster
   (libc64/raster, qui s'appuie sur libc64/irq).

   N'utilise de libc64 que screen_*, wait_frame, sprite_load/show/move,
   joy2_read, sid_* et raster/irq : rnd8 et sprite_hide ne sont pas
   incorporés au programme (voir build/demo.map, rubrique « Modules list »). */
#include <c64.h>
#include "libc64.h"

#define X_MIN 24        /* bord gauche visible */
#define X_MAX 320       /* bord droit (sprite de 24 pixels) */
#define Y_MIN 50
#define Y_MAX 229
#define SHIP_BLOCK 13   /* motif en $0340 (13 * 64) */
#define NOTE_440 0x1D45
#define BAND_LINE 141   /* ligne raster : milieu de l'écran visible (51-250) */
#define BAND_HEIGHT 3
#define BAND_COLOR COLOR_BLUE

static const unsigned char ship[63] = {
    0x00, 0x18, 0x00,  0x00, 0x3C, 0x00,  0x00, 0x7E, 0x00,  0x00, 0x66, 0x00,
    0x00, 0xE7, 0x00,  0x01, 0xFF, 0x80,  0x03, 0xFF, 0xC0,  0x07, 0xDB, 0xE0,
    0x0F, 0xDB, 0xF0,  0x1F, 0xFF, 0xF8,  0x3F, 0xFF, 0xFC,  0x7F, 0xFF, 0xFE,
    0xFF, 0xFF, 0xFF,  0xFC, 0x3C, 0x3F,  0xF8, 0x18, 0x1F,  0xF0, 0x18, 0x0F,
    0x60, 0x18, 0x06,  0x00, 0x3C, 0x00,  0x00, 0x7E, 0x00,  0x00, 0x66, 0x00,
    0x00, 0x42, 0x00,
};

/* Bande : le fond change de couleur à BAND_LINE et redevient noir
   BAND_HEIGHT lignes plus bas. Appelés sous interruption : très courts. */
static void band_on(void)
{
    VIC.bgcolor0 = BAND_COLOR;
}

static void band_off(void)
{
    VIC.bgcolor0 = COLOR_BLACK;
}

/* Globales : visibles dans le débogueur (VS Code, portail). */
unsigned int ship_x = 172;
unsigned char ship_y = 150;
unsigned int frames;

int main(void)
{
    unsigned char joy, prev = 0;

    screen_colors(COLOR_BLACK, COLOR_BLACK);
    screen_clear(COLOR_WHITE);
    screen_print(13, 1, "MyGame - demo");
    screen_print(4, 23, "Joystick 2 : deplacer, Feu : son");
    sid_init();
    sprite_load(0, SHIP_BLOCK, ship);
    sprite_show(0, COLOR_YELLOW);
    raster_register(BAND_LINE, band_on);
    raster_register(BAND_LINE + BAND_HEIGHT, band_off);

    for (;;) {
        wait_frame();
        ++frames;
        joy = joy2_read();
        if ((joy & J_LEFT) && ship_x > X_MIN) --ship_x;
        if ((joy & J_RIGHT) && ship_x < X_MAX) ++ship_x;
        if ((joy & J_UP) && ship_y > Y_MIN) --ship_y;
        if ((joy & J_DOWN) && ship_y < Y_MAX) ++ship_y;
        sprite_move(0, ship_x, ship_y);
        if ((joy & J_FIRE) && !(prev & J_FIRE)) {
            sid_beep(NOTE_440);
        } else if (!(joy & J_FIRE) && (prev & J_FIRE)) {
            sid_release();
        }
        prev = joy;
    }
    return 0;
}
