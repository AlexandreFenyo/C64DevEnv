/* libtest.c - vérifie toutes les fonctions de libc64 (utilisé par le test 6).
   Résultats en mémoire (globales lues par le test avec dbg.py), puis
   test_done = 1 et boucle infinie. */
#include <c64.h>
#include "libc64.h"

static const unsigned char pattern[63] = { 0xFF, 0x81, 0x42 };

unsigned char test_done;
unsigned char rnd_values[4];
unsigned char rnd_period_ok;    /* 1 si rnd8 revient à sa 1re valeur après 255 tirages, pas avant */
unsigned char spr_after_show;   /* $D015 après sprite_show(3) */
unsigned char spr_after_hide;   /* $D015 après sprite_hide(3) */
unsigned char hi_after_move;    /* $D010 après sprite_move(3, 300, 100) */
unsigned char joy_idle;         /* joy2_read() sans manette : 0 attendu */
unsigned int frames_waited;

int main(void)
{
    unsigned char i, first;
    unsigned int n;

    screen_colors(COLOR_BLUE, COLOR_BLACK);
    screen_clear(COLOR_GREEN);
    screen_print(0, 0, "libc64 OK?");
    sprite_load(3, 14, pattern);
    sprite_show(3, COLOR_RED);
    spr_after_show = VIC.spr_ena;
    sprite_move(3, 300, 100);
    hi_after_move = VIC.spr_hi_x;
    sprite_hide(3);
    spr_after_hide = VIC.spr_ena;
    joy_idle = joy2_read();
    sid_init();
    sid_beep(0x1D45);
    sid_release();
    for (i = 0; i < 4; ++i) {
        rnd_values[i] = rnd8();
    }
    first = rnd8();
    for (n = 1; n < 255 && rnd8() != first; ++n) {
    }
    rnd_period_ok = (n == 255);
    for (i = 0; i < 5; ++i) {
        wait_frame();
        ++frames_waited;
    }
    test_done = 1;
    for (;;) {
    }
    return 0;
}
