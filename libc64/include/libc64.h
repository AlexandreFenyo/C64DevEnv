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

/* --- Interruptions (libc64/irq) -------------------------------------------
   Le vecteur IRQ du KERNAL ($0314) est redirigé vers un répartiteur qui
   appelle les handlers enregistrés dont les sources correspondent à
   l'interruption, puis rend la main au KERNAL (CIA : clavier, horloge) ou
   termine l'interruption (VIC-II, acquittée par le répartiteur).
   Table de taille fixe ; un handler peut s'enregistrer de nouveau ou se
   désenregistrer depuis l'interruption. Les registres de page zéro du C sont
   sauvegardés : un handler peut être une fonction C (courte !). */
#define IRQ_MAX_HANDLERS 4
#define IRQ_SRC_CIA 0x01        /* timer du CIA 1 : IRQ du KERNAL, 60 Hz */
#define IRQ_SRC_VIC 0x02        /* VIC-II : raster, collisions */
typedef void (*irq_handler_t)(void);
/* Installe le répartiteur (appelé aussi par irq_register). [asm] */
void irq_init(void);
/* Remet le vecteur d'origine et coupe l'IRQ raster : avant de rendre la
   main au BASIC. [asm] */
void irq_done(void);
/* Enregistre h pour les sources données (IRQ_SRC_*) : renvoie l'indice de
   l'emplacement, ou 0xFF si la table est pleine. Déjà enregistré : mise à
   jour des sources, même emplacement. [asm] */
unsigned char __fastcall__ irq_register(irq_handler_t h, unsigned char sources);
/* Retire h de la table (sans effet s'il n'y est pas). [asm] */
void __fastcall__ irq_unregister(irq_handler_t h);
/* Contenu de $D019 lu pour l'interruption VIC-II en cours (bit 0 : raster). */
extern unsigned char irq_vic_flags;

/* --- Lignes raster (libc64/raster) ------------------------------------------
   Appelle un handler quand le balayage atteint une ligne donnée (de
   RASTER_LEAD à 311 en PAL ; écran visible : lignes 51 à 250). S'appuie sur
   irq. L'interruption est demandée RASTER_LEAD lignes avant et la
   bibliothèque attend la ligne exacte : le handler démarre au début de sa
   ligne, à quelques cycles près, quel que soit le temps pris par le KERNAL et
   le répartiteur. Deux handlers proches s'enchaînent sans nouvelle
   interruption. Table de taille fixe. */
#define RASTER_MAX_HANDLERS 4
#define RASTER_LEAD 8
/* Enregistre h à la ligne line (déjà enregistré : change sa ligne). Renvoie
   0, ou 0xFF si la table est pleine. Utilisable depuis un handler (pour se
   déplacer à une autre ligne ; coût : quelques lignes raster, laisser de la
   marge avant le handler suivant). [asm] */
unsigned char __fastcall__ raster_register(unsigned int line, irq_handler_t h);
/* Retire h ; plus aucun handler : l'IRQ raster est coupée. [asm] */
void __fastcall__ raster_unregister(irq_handler_t h);

/* --- Tileset du jeu (libc64/tileset) ------------------------------------------
   Jeu de caractères décrit dans libc64/tileset/tileset.txt (182 tiles
   $40-$FB, noms TILE_* et couleurs TC_* dans tiles.h, générés par
   tools/mktileset.py). Fond vert clair ($D021), gris et blanc partagés
   ($D022/$D023), mode multicolore case par case : une case est multicolore
   si sa Color RAM vaut 8 + couleur (0-7). */
/* Mémoire vidéo en banque VIC 3 ($C000-$FFFF) : écran en $C000, second écran
   réservé en $C400 (double tampon du défilement), jeu de caractères en
   $C800. Les programmes sont liés avec __HIMEM__ = $C000 (Makefile) : le
   programme, sa pile C et ses données s'arrêtent avant ; l'éditeur de liens
   refuse un programme trop gros. Color RAM : toujours $D800. */
#define TILESET_SCREEN  0xC000
#define TILESET_SCREEN2 0xC400
#define TILESET_CHARSET 0xC800
/* Copie les motifs en $C800, passe le VIC-II en banque 3 (écran $C000) et
   règle les couleurs. Renvoie 0, ou 0xFF si le programme déborde sur $C000
   (impossible avec __HIMEM__ = $C000 : garde-fou). */
unsigned char tileset_install(void);
/* Rend la banque 0, l'écran $0400, la ROM de caractères ; coupe le multicolore. */
void tileset_done(void);
/* Color RAM par défaut du tile (celle de sa palette ; 8 + couleur en MC). */
unsigned char __fastcall__ tile_color(unsigned char code);
/* Pose un tile en (x, y) avec sa Color RAM par défaut / imposée. */
void __fastcall__ tile_put(unsigned char x, unsigned char y, unsigned char code);
void __fastcall__ tile_put_color(unsigned char x, unsigned char y, unsigned char code,
                                 unsigned char color);
/* Tout l'écran avec un tile (Color RAM par défaut). */
void __fastcall__ tile_fill(unsigned char code);

/* --- Monde du jeu (libc64/world) ----------------------------------------------
   Carte de WORLD_W x WORLD_H tiles (constantes dans world.h), importée de la
   carte HTML (libc64/world/world.txt) et compressée par tools/mkworld.py
   (~20 Ko : jetons en quartets, segments de 20 colonnes partagés). Affichage dans l'écran du tileset (TILESET_SCREEN, $C000) :
   appeler tileset_install() d'abord. */
/* Fenêtre 40x25 dont le coin haut gauche est la case (x, y), ramenée dans
   [0, WORLD_MAX_X] x [0, WORLD_MAX_Y]. Environ 3 images. [asm] */
void __fastcall__ world_draw(unsigned int x, unsigned char y);
/* Code de tile de la case (x, y) ; 0 hors du monde. [asm] */
unsigned char __fastcall__ world_tile(unsigned int x, unsigned char y);

/* Défilement fin (au pixel), double tampon (écrans $C000/$C400), dans le
   haut de l'écran : WORLD_SCROLL_ROWS lignes de caractères, 304 x 121 pixels
   visibles (38 colonnes, lignes raster 55 à 175) ; le bas est au panneau
   (libc64/panel, panel_init()). Position = coin haut gauche visible, en
   pixels du monde. Le déplacement est appliqué à chaque image par un handler
   raster (ligne 250, libc64/raster) ; le programme prépare la vue suivante
   en appelant world_scroll_work() en boucle. [C + asm]
   Vitesse de -7 à 7 ; sans attente jusqu'à 2 (mesuré). */
#define WORLD_SCROLL_ROWS   16      /* lignes de caractères de la vue */
#define WORLD_SCROLL_VIEW_H 121     /* hauteur visible, en pixels */
#include "world.h"
#define WORLD_SCROLL_MAX_PX (WORLD_W * 8u - 304)   /* largeur du monde - largeur visible */
#define WORLD_SCROLL_MAX_PY (WORLD_H * 8u - WORLD_SCROLL_VIEW_H)
extern unsigned int world_px, world_py;      /* position courante */
extern signed char world_scroll_dx, world_scroll_dy;   /* vitesse voulue (pixels/image) */
extern unsigned int world_scroll_stalls;     /* images où la vue suivante n'était pas prête */
extern unsigned int world_scroll_frames;     /* images traitées */
extern unsigned char world_scroll_bumps;     /* images où la vue a buté sur un bord */
extern unsigned char world_scroll_front;     /* écran affiché : 0 = $C000, 1 = $C400 */
/* Mesure du temps processeur : couleur du tour de l'écran ($D020) pendant
   chaque étape de world_scroll_work() (WORLD_SCROLL_NO_METER : pas de
   mesure, défaut). */
#define WORLD_SCROLL_NO_METER 0xFF
extern unsigned char world_scroll_meter;
/* Affiche la vue en (px, py) (bornée, ~4 images) et démarre le handler. */
void __fastcall__ world_scroll_init(unsigned int px, unsigned int py);
/* Arrête le handler (la vue reste affichée). */
void world_scroll_done(void);
/* Prépare la vue suivante, une étape par appel (copie décalée ~23 000
   cycles, nouvelle ligne ~3 500, nouvelle colonne ~9 000) ; 0 s'il n'y a rien
   à faire. À appeler en boucle dans la boucle principale du programme. */
unsigned char world_scroll_work(void);

/* --- Panneau du bas de l'écran (libc64/panel) ---------------------------
   Sous la vue qui défile (world_scroll), une bande noire de 8 lignes raster
   (176-183) puis PANEL_ROWS lignes de texte (raster 184-246) dans le jeu de
   caractères du système (ROM minuscules/majuscules, copiée en RAM $E800 :
   la banque VIC 3 ne voit pas la ROM), écran $F000, 40 colonnes, fond noir.
   Deux handlers raster (lignes 174 et 182) changent le mode du VIC-II au
   cycle près ; le handler de world_scroll rétablit le haut de l'écran à la
   ligne 250. Appeler après tileset_install(). [asm + C] */
#define PANEL_ROW  16               /* ligne de l'écran $F000 où commence le panneau */
#define PANEL_ROWS 8
#define PANEL_SCREEN ((unsigned char *)0xF000)
/* Copie le jeu de caractères, efface le panneau (couleur du texte : color)
   et enregistre les deux handlers. [asm] */
void __fastcall__ panel_init(unsigned char color);
/* Retire les handlers. [asm] */
void panel_done(void);
/* Texte colonne x (0-39), ligne y (0 à PANEL_ROWS-1) du panneau ; même
   conversion que screen_print (écrire en casse normale). [C] */
void __fastcall__ panel_print(unsigned char x, unsigned char y, const char *s);
/* Efface le panneau (espaces). [C] */
void panel_clear(void);

/* --- Hasard (libc64/random) ---------------------------------------------- */
/* Nombre pseudo-aléatoire 1-255 (registre à décalage, période 255). [asm] */
unsigned char rnd8(void);

#endif
