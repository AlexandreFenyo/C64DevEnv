/* libc64.h - bibliothèque de fonctions C64 du dépôt (libc64/).
 *
 * Une fonction = un fichier source = un module de build/libc64.lib : l'éditeur
 * de liens (ld65) n'incorpore dans un programme que les modules qu'il appelle.
 * Les fonctions écrites en assembleur sont appelables depuis le C (convention
 * __fastcall__ de cc65 : dernier argument dans A/X, les autres sur la pile C).
 *
 * Usage en C : #include "libc64.h" (le Makefile ajoute -I libc64/include).
 * Usage en assembleur : .include "libc64.inc", puis jsr _nom.
 */
#ifndef LIBC64_H
#define LIBC64_H

/* --- Écran (libc64/screen) ----------------------------------------------- */
/* Efface l'écran texte ($0400) et remplit la mémoire couleur ($D800). [asm] */
void __fastcall__ screen_clear(unsigned char color);
/* Couleurs de la bordure et du fond. [C] */
void __fastcall__ screen_colors(unsigned char border, unsigned char background);
/* Écrit une chaîne colonne x (0-39), ligne y (0-24), sans toucher aux
   couleurs. Un programme C tourne avec le jeu de caractères minuscules/
   majuscules (le runtime cc65 met $D018 à $17) : écrire le texte normalement,
   « Score : 10 ». En assembleur (jeu majuscules/graphiques), écrire en
   minuscules dans le source pour obtenir des majuscules. [C] */
void __fastcall__ screen_print(unsigned char x, unsigned char y, const char *s);

/* --- Temps (libc64/time) ------------------------------------------------- */
/* Attend le début de la ligne raster 250 : une fois par image (50 Hz). [asm] */
void wait_frame(void);

/* --- Sprites (libc64/sprite) --------------------------------------------- */
/* Copie 63 octets de motif dans le bloc `block` (adresse block * 64 de la
   banque VIC 0, ex. 13 = $0340) et y fait pointer le sprite n. [C] */
void __fastcall__ sprite_load(unsigned char n, unsigned char block, const unsigned char *data);
/* Active le sprite n avec la couleur donnée. [C] */
void __fastcall__ sprite_show(unsigned char n, unsigned char color);
/* Désactive le sprite n. [C] */
void __fastcall__ sprite_hide(unsigned char n);
/* Position du sprite n : x sur 9 bits (0-511, bit 9 dans $D010), y. [asm] */
void __fastcall__ sprite_move(unsigned char n, unsigned int x, unsigned char y);

/* --- Manettes (libc64/input) --------------------------------------------- */
#define J_UP    0x01
#define J_DOWN  0x02
#define J_LEFT  0x04
#define J_RIGHT 0x08
#define J_FIRE  0x10
/* État de la manette du port 2 : combinaison de J_* (1 = actionné). [asm] */
unsigned char joy2_read(void);

/* --- Son (libc64/sound) -------------------------------------------------- */
/* Remet le SID à zéro, volume maximal. [C] */
void sid_init(void);
/* Note sur la voix 1 (triangle) : freq = Hz * 17,03 en PAL. [C] */
void __fastcall__ sid_beep(unsigned int freq);
/* Relâche la note de la voix 1 (gate fermé). [C] */
void sid_release(void);

/* --- Hasard (libc64/random) ---------------------------------------------- */
/* Nombre pseudo-aléatoire 1-255 (registre à décalage, période 255). [asm] */
unsigned char rnd8(void);

#endif
