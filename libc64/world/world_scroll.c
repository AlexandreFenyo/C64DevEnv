/* world_scroll.c - défilement fin (au pixel) du monde, double tampon.

   Affichage : le VIC-II décale l'image de 0 à 7 pixels ($D016 bits 0-2,
   $D011 bits 0-2) ; en 38 colonnes et 24 lignes, les bords masquent les cases
   partiellement visibles : la fenêtre visible fait 304 x 192 pixels.

   Deux moitiés :
   - un handler raster en assembleur (world_scroll_irq.s, ligne 250, début du
     balayage vertical) fait avancer la position de (world_scroll_dx,
     world_scroll_dy) pixels à CHAQUE image, quoi que fasse le programme :
     décalage fin, et au franchissement d'une case, bascule vers l'écran
     caché ($D018) et copie des couleurs préparées dans la Color RAM ; puis il
     désigne la vue de la PROCHAINE case selon la direction (ws_back_*) ;
   - le programme appelle world_scroll_work() en boucle : cette vue se
     prépare dans l'écran caché en trois étapes : copie décalée d'une case de
     l'écran affiché et de ses couleurs (world_copy2, ~23 000 cycles), puis
     décodage de la seule ligne (40 cases) et/ou colonne (25 cases) qui
     apparaît. Une étape est abandonnée si la cible a changé pendant ce temps
     (ws_gen).
   Si la vue n'est pas prête au franchissement (départ à 1 pixel d'une case,
   changement de direction juste avant), la position attend
   (world_scroll_stalls). */
#include <c64.h>
#include "libc64.h"
#include "world.h"

#define SCROLL_LINE 250                      /* ligne raster du handler */
#define SEI() __asm__ ("sei")
#define CLI() __asm__ ("cli")

/* world_render.s, world_render_col.s, world_shift.s, world_colorcopy.s */
extern unsigned int wr_tx;
extern unsigned char wr_ty;
extern unsigned char *wr_screen, *wr_colors;
extern unsigned char *wc_src1, *wc_dst1, *wc_src2, *wc_dst2;
void __fastcall__ world_render_rows(unsigned char row0, unsigned char n);
void __fastcall__ world_render_col(unsigned char col);
void __fastcall__ world_copy2(unsigned int n);
void __fastcall__ world_color_copy(const unsigned char *src);

/* world_scroll_irq.s : handler et état partagé (lu ici sous SEI). */
void world_scroll_irq(void);
void ws_apply_fine(void);
extern unsigned int ws_cur_tx, ws_back_tx;   /* case affichée, vue en préparation ($FFFF : aucune) */
extern unsigned char ws_cur_ty, ws_back_ty;
extern unsigned char ws_back_step, ws_gen;   /* étape de préparation, génération de la cible */
extern unsigned char *ws_front_colors, *ws_back_colors;

unsigned char world_scroll_meter = WORLD_SCROLL_NO_METER;

#define STEP_COPY 0                          /* étapes de préparation */
#define STEP_ROW  1
#define STEP_COL  2
#define STEP_DONE 3

static unsigned char *screen_of(unsigned char s)
{
    return (unsigned char *)(s ? TILESET_SCREEN2 : TILESET_SCREEN);
}

void __fastcall__ world_scroll_init(unsigned int px, unsigned int py)
{
    raster_unregister(world_scroll_irq);
    if (px > WORLD_SCROLL_MAX_PX) px = WORLD_SCROLL_MAX_PX;
    if (py > WORLD_SCROLL_MAX_PY) py = WORLD_SCROLL_MAX_PY;
    world_px = px;
    world_py = py;
    ws_cur_tx = px >> 3;
    ws_cur_ty = py >> 3;
    world_scroll_front = 0;
    wr_tx = ws_cur_tx;
    wr_ty = ws_cur_ty;
    wr_screen = screen_of(0);
    wr_colors = ws_front_colors;
    world_render_rows(0, 25);
    world_color_copy(ws_front_colors);
    VIC.addr = 0x02;                         /* écran $C000, motifs $C800 */
    ws_apply_fine();
    ws_back_tx = 0xFFFF;
    raster_register(SCROLL_LINE, world_scroll_irq);
}

void world_scroll_done(void)
{
    raster_unregister(world_scroll_irq);
}

unsigned char world_scroll_work(void)
{
    unsigned char gen, step, ty, front, bg;
    unsigned int tx;
    int off;
    signed char sx, sy;
    unsigned char *fscr, *bscr, *fcol, *bcol;

    SEI();
    gen = ws_gen;
    step = ws_back_step;
    tx = ws_back_tx;
    ty = ws_back_ty;
    front = world_scroll_front;
    fcol = ws_front_colors;
    bcol = ws_back_colors;
    sx = (signed char)(tx - ws_cur_tx);
    sy = (signed char)(ty - ws_cur_ty);
    CLI();
    if (tx == 0xFFFF || step == STEP_DONE) {
        return 0;
    }
    bg = VIC.bgcolor0;
    if (world_scroll_meter != WORLD_SCROLL_NO_METER) {
        VIC.bgcolor0 = world_scroll_meter;   /* mesure : fond coloré pendant l'étape */
    }
    fscr = screen_of(front);
    bscr = screen_of(front ^ 1);
    wr_tx = tx;
    wr_ty = ty;
    wr_screen = bscr;
    wr_colors = bcol;
    if (step == STEP_COPY) {
        /* vue cible[i] = vue affichée[i + off] : copie linéaire ; les cases
           qui débordent d'une ligne sur l'autre sont celles de la nouvelle
           colonne, réécrites ensuite. */
        off = sy * 40 + sx;
        if (off >= 0) {
            wc_dst1 = bscr; wc_src1 = fscr + off;
            wc_dst2 = bcol; wc_src2 = fcol + off;
        } else {
            wc_dst1 = bscr - off; wc_src1 = fscr;
            wc_dst2 = bcol - off; wc_src2 = fcol;
        }
        world_copy2(1000 - (off >= 0 ? off : -off));
    } else if (step == STEP_ROW) {
        if (sy) {
            world_render_rows(sy > 0 ? 24 : 0, 1);
        }
    } else {
        if (sx) {
            world_render_col(sx > 0 ? 39 : 0);
        }
    }
    SEI();
    if (gen == ws_gen && ws_back_step == step) {
        ws_back_step = step + 1;                /* étape valide : la cible n'a pas changé */
    }
    CLI();
    VIC.bgcolor0 = bg;
    return 1;
}
