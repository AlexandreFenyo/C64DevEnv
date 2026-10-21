/* tiles_demo.c - vitrine du tileset de libc64 : catalogue des 182 tiles (lignes
   0 à 4, couleurs par défaut) et assemblages de tileset.txt (section 6) : route,
   maisons, voitures, feu, lac, piscine, logo, panneau, arbres, drapeau, texte.
   Sert aussi au test 6 (contenu de l'écran, registres, rendu). */
#include <c64.h>
#include "libc64.h"
#include "tiles.h"

unsigned char install_result = 0xEE;     /* lu par le test */

/* Bloc w x h de codes (ligne par ligne), couleurs par défaut. */
static void block(unsigned char x, unsigned char y, unsigned char w, unsigned char h,
                  const unsigned char *codes)
{
    unsigned char i, j;

    for (j = 0; j < h; ++j) {
        for (i = 0; i < w; ++i) {
            tile_put(x + i, y + j, *codes++);
        }
    }
}

/* Texte avec la police du tileset (A-Z en $90-$A9, espace = case laissée). */
static void text(unsigned char x, unsigned char y, const char *s, unsigned char color)
{
    for (; *s; ++s, ++x) {
        if (*s >= 'a' && *s <= 'z') {
            tile_put_color(x, y, TILE_A + (*s - 'a'), color);
        }
    }
}

static const unsigned char maison3x2[] = { TILE_TOIT_PENTE_G, TILE_TOIT_PLEIN, TILE_TOIT_PENTE_D,
                                           TILE_FENETRE_CYAN, TILE_FENETRE_CYAN, TILE_PORTE_NOIRE };
static const unsigned char maison2x2[] = { TILE_TOIT_PENTE_G, TILE_TOIT_PENTE_D,
                                           TILE_FENETRE_CYAN, TILE_PORTE_NOIRE };
static const unsigned char garage[] = { TILE_GARAGE_HG, TILE_GARAGE_HM, TILE_GARAGE_HD,
                                        TILE_GARAGE_BG, TILE_GARAGE_BM, TILE_GARAGE_BD };
static const unsigned char voiture[] = { TILE_VOITURE_HG, TILE_VOITURE_HD, TILE_VOITURE_MG,
                                         TILE_VOITURE_MD, TILE_VOITURE_BG, TILE_VOITURE_BD };
static const unsigned char lac[] = { TILE_LAC_NO, TILE_LAC_BORD_H, TILE_LAC_BORD_H, TILE_LAC_NE,
                                     TILE_LAC_BORD_G, TILE_EAU, TILE_EAU, TILE_LAC_BORD_D,
                                     TILE_LAC_SO, TILE_LAC_BORD_B, TILE_LAC_BORD_B, TILE_LAC_SE };
static const unsigned char piscine[] = { TILE_PISC_COIN_NO, TILE_PISC_BORD_H, TILE_PISC_COIN_NE,
                                         TILE_PISC_COIN_SO, TILE_PISC_BORD_B, TILE_PISC_COIN_SE };
static const unsigned char panneau[] = { TILE_PANNEAU_PARKING_HG, TILE_PANNEAU_PARKING_HD,
                                         TILE_PANNEAU_PARKING_BG, TILE_PANNEAU_PARKING_BD };

int main(void)
{
    unsigned char i, code;

    install_result = tileset_install();
    if (install_result != 0) {
        VIC.bordercolor = COLOR_RED;        /* programme trop gros pour $C000 */
        for (;;) {
        }
    }
    VIC.bordercolor = COLOR_BLACK;
    tile_fill(TILE_VIDE);

    /* Catalogue : codes $40-$FB, 40 par ligne (trous $8A-$8F : vides). */
    for (code = TILE_FIRST, i = 0; code <= TILE_LAST; ++code, ++i) {
        tile_put(i % 40, i / 40, code);
    }

    text(1, 6, "tileset", TC_NOIR);
    text(10, 6, "c", TC_BLEU);
    text(11, 6, "sixty", TC_ROUGE);
    text(17, 6, "four", TC_VIOLET);

    /* Route horizontale (lignes 13-15) : bords, tirets centraux. */
    for (i = 0; i < 40; ++i) {
        tile_put(i, 13, TILE_ROUTE_HH);
        tile_put(i, 14, (i & 2) ? TILE_ROUTE_TIRET_HAUT : TILE_ROUTE_V);
        tile_put(i, 15, TILE_ROUTE_HB);
    }

    block(1, 9, 3, 2, maison3x2);
    block(5, 9, 2, 2, maison2x2);
    block(8, 9, 3, 2, garage);
    for (i = 0; i < 6; ++i) {               /* arbres et champ de blé */
        tile_put(12 + i, 10, TILE_ARBRE_ROND + i % 3);
        tile_put(12 + i, 11, TILE_CHAMP_BLE);
    }
    tile_put(20, 10, TILE_FEU_HAUT_ROUGE);  /* feu tricolore */
    tile_put(20, 11, TILE_FEU_BAS_VERT);
    tile_put(22, 10, TILE_FEU_HAUT_VERT);
    tile_put(22, 11, TILE_FEU_BAS_VERT);
    block(24, 10, 2, 2, panneau);
    tile_put_color(28, 9, TILE_PLEIN, TC_BLEU);     /* drapeau : PLEIN en Color RAM libre */
    tile_put_color(29, 9, TILE_PLEIN, TC_BLANC);
    tile_put_color(30, 9, TILE_PLEIN, TC_ROUGE);
    tile_put(28, 10, TILE_POTEAU);
    tile_put(28, 11, TILE_POTEAU);

    /* Voitures sur la route : carrosserie = Color RAM (8 + couleur : multicolore). */
    block(4, 17, 2, 3, voiture);
    for (i = 0; i < 6; ++i) {
        *((unsigned char *)0xD800 + (17 + i / 2) * 40 + 8 + i % 2) = 8 + TC_BLEU;
        *((unsigned char *)TILESET_SCREEN + (17 + i / 2) * 40 + 8 + i % 2) = voiture[i];
    }

    block(12, 17, 4, 3, lac);
    block(18, 17, 3, 2, piscine);
    for (i = 0; i < 9; ++i) {               /* logo Pomme 3x3 : codes consécutifs */
        tile_put(23 + i % 3, 17 + i / 3, TILE_LOGO_POMME_HG + i);
    }
    for (i = 0; i < 9; ++i) {               /* logo Gwen */
        tile_put(28 + i % 3, 17 + i / 3, TILE_LOGO_GWEN_HG + i);
    }
    text(1, 22, "parking", TC_BLEU);
    text(10, 22, "hopital", TC_ROUGE);
    for (;;) {
    }
    return 0;
}
