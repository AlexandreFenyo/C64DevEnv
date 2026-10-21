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

/* irq / raster */
unsigned char cia_count;        /* handler CIA qui se réenregistre à chaque appel */
unsigned char cia_slot, cia_slot_again;
unsigned char irq_full;         /* irq_register sur table pleine : 0xFF attendu */
unsigned char line_a, line_b;   /* lignes observées par les handlers de 100 et 103 */
unsigned char count_a, count_b;
unsigned char count_a_frozen;   /* count_a au moment du désenregistrement */
unsigned char mover_lines[2];   /* handler qui se déplace 120 <-> 130 */
unsigned char raster_full;      /* raster_register sur table pleine : 0xFF attendu */

static unsigned char mover_state;

static void on_cia(void)
{
    ++cia_count;
    cia_slot_again = irq_register(on_cia, IRQ_SRC_CIA);
}

static void at_a(void) { line_a = VIC.rasterline; ++count_a; }
static void at_b(void) { line_b = VIC.rasterline; ++count_b; }

static void mover(void)
{
    mover_lines[mover_state] = VIC.rasterline;
    mover_state ^= 1;
    raster_register(mover_state ? 130 : 120, mover);
}

static void dummy1(void) { }
static void dummy2(void) { }
static void dummy3(void) { }

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

    /* irq : table fixe, réenregistrement depuis le handler. */
    cia_slot = irq_register(on_cia, IRQ_SRC_CIA);
    raster_register(100, at_a);              /* occupe aussi un emplacement irq */
    raster_register(103, at_b);
    raster_register(120, mover);
    raster_register(200, dummy1);            /* 4e emplacement raster */
    raster_full = raster_register(210, dummy2);
    raster_unregister(dummy1);
    irq_register(dummy1, IRQ_SRC_CIA);
    irq_register(dummy2, IRQ_SRC_CIA);       /* table irq pleine (4) */
    irq_full = irq_register(dummy3, IRQ_SRC_CIA);
    irq_unregister(dummy1);
    irq_unregister(dummy2);
    for (i = 0; i < 20; ++i) {
        wait_frame();
    }
    raster_unregister(at_a);
    count_a_frozen = count_a;
    for (i = 0; i < 10; ++i) {
        wait_frame();
    }
    test_done = 1;
    for (;;) {
    }
    return 0;
}
