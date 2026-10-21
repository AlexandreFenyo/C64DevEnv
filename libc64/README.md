# libc64 : bibliothèque de fonctions C64

Fonctions réutilisables par les programmes du dépôt (`mygame/`, `src/`, `examples/`), écrites en C ou en assembleur selon les besoins (vitesse, accès matériel).

## Principe : on ne paie que ce qu'on utilise

- **Un sous-répertoire par thème** : `screen/`, `sprite/`, `input/`, `time/`, `sound/`, `random/`, `irq/`, `raster/`, `tileset/`, `world/`, `panel/`.
- **Un fichier par fonction** : chaque fichier devient un module de l'archive `build/libc64.lib` (construite par `make`).
- Chaque programme est lié avec cette archive. L'éditeur de liens `ld65` **n'y prend que les modules appelés** : une fonction inutilisée n'occupe aucun octet dans le `.prg`. Liste de ce qui a été incorporé : `build/<prog>.map`, rubrique « Modules list », lignes `libc64.lib(...)`.

## Utilisation

En C :

```c
#include "libc64.h"     /* -I libc64/include est ajouté par le Makefile */

screen_clear(COLOR_WHITE);
screen_print(0, 0, "Score : 0");
```

En assembleur (ca65) :

```asm
.include "libc64.inc"
        jsr _wait_frame
        lda #1          ; couleur blanche
        jsr _screen_clear
```

Les fonctions asm suivent la convention `__fastcall__` de cc65 : dernier argument dans A (octet) ou A/X (mot), les autres sur la pile logicielle de cc65.

## Fonctions

| Thème | Fonction | Langage | Rôle |
|---|---|---|---|
| screen | `screen_clear(color)` | asm | écran texte rempli d'espaces, mémoire couleur remplie |
| screen | `screen_colors(border, background)` | C | couleurs de bordure et de fond |
| screen | `screen_print(x, y, s)` | C | chaîne à l'écran (conversion en codes écran) |
| time | `wait_frame()` | asm | attend la ligne raster 250 : une fois par image (50 Hz) |
| sprite | `sprite_load(n, block, data)` | C | copie un motif de 63 octets en `block * 64`, pointeur du sprite n |
| sprite | `sprite_show(n, color)` / `sprite_hide(n)` | C | active (avec sa couleur) / désactive le sprite n |
| sprite | `sprite_move(n, x, y)` | asm | position, x sur 9 bits (bit 9 dans `$D010`) |
| input | `joy2_read()` | asm | manette port 2 : bits `J_UP`, `J_DOWN`, `J_LEFT`, `J_RIGHT`, `J_FIRE` |
| sound | `sid_init()` / `sid_beep(freq)` / `sid_release()` | C | SID à zéro ; note sur la voix 1 ; relâchement |
| random | `rnd8()` | asm | nombre pseudo-aléatoire 1-255 |
| irq | `irq_register(h, sources)` / `irq_unregister(h)` / `irq_init()` / `irq_done()` | asm | répartiteur d'interruptions, table fixe de `IRQ_MAX_HANDLERS` handlers |
| raster | `raster_register(line, h)` / `raster_unregister(h)` | asm | handler appelé à une ligne raster, table fixe de `RASTER_MAX_HANDLERS` |

| tileset | `tileset_install()` / `tileset_done()` | C | jeu de caractères du jeu de conduite en `$C800`, écran en `$C000` (banque VIC 3) + couleurs du VIC-II |
| tileset | `tile_put(x, y, code)` / `tile_put_color(x, y, code, color)` / `tile_fill(code)` / `tile_color(code)` | C | poser des tiles avec leur Color RAM par défaut ou imposée |

### Tileset du jeu (`tileset`)

- **Source unique** : `libc64/tileset/tileset.txt`, la description fournie (configuration VIC-II, palette, palettes P01-P14, 182 tiles `$40`-`$FB`, assemblages, auto-tiling de l'eau). `tools/mktileset.py` en génère `tileset/tileset_data.s` (motifs + Color RAM par défaut), `include/tiles.h` et `include/tiles.inc` (`TILE_HERBE`, `TILE_LOGO_POMME_HG`…, couleurs `TC_VERT_CLAIR`…, `TILESET_BG/MC1/MC2`). Modifier un tile : éditer `tileset.txt`, puis `make` (régénération automatique). Les fichiers générés sont versionnés ; le test 6 vérifie qu'ils sont à jour.
- **Mémoire vidéo en banque VIC 3** : écran en **`$C000`** (`TILESET_SCREEN`), second écran en `$C400` (double tampon du défilement au pixel, `world_scroll_*`), motifs en **`$C800`** (`TILESET_CHARSET`). Le Makefile lie tous les programmes avec `__HIMEM__ = $C000` : programme, données et pile C tiennent dans `$0801`-`$BFFF` (≈ 45 Ko ; le runtime cc65 coupe la ROM BASIC), et l'éditeur de liens refuse un programme trop gros. `tileset_install()` copie les motifs, sélectionne la banque 3 (`$DD00`), pointe `$D018` sur l'écran et les motifs, met `$D021`=13, `$D022`=11, `$D023`=1, active le multicolore (`$D016` bit 4) et place la page écran du KERNAL (`$0288`) en `$C0`. `tile_put`, `tile_fill` écrivent dans cet écran ; les fonctions `screen_*` restent sur l'écran `$0400` du KERNAL. Sprites : leurs motifs doivent alors être dans la banque 3 (pointeurs en `$C3F8`), `sprite_load` ne le gère pas encore.
- **Color RAM par défaut** d'un tile = couleur de sa palette : STD → couleur du bit 1 ; MC → 8 + couleur du couple `11` (le bit 3 rend la case multicolore). `tile_put_color` impose une autre valeur (convention `{tile, colorRam}` de la carte, ex. carrosserie d'une voiture : `8 + TC_BLEU`).
- **Écarts de la description, signalés par le générateur** : la Color RAM ne fournit que les couleurs 0-7. P13 (`1=ROSE`, couleur 10) est donc irréalisable : les tiles `$E4`-`$E6` (LeCat, rangée du milieu) prennent la couleur réalisable la plus proche, **VIOLET (4)**. P06 (`11=GRIS`) l'est aussi, mais ses deux tiles (`$5A`, `$5E`) n'ont aucun pixel `11` : sans effet.
- Vitrine : `examples/tileset_demo` (catalogue + assemblages).

| world | `world_draw(x, y)` / `world_tile(x, y)` | asm | monde du jeu : vue 40x25 à la case (x, y), code d'une case |
| world | `world_scroll_init(px, py)` / `world_scroll_work()` / `world_scroll_done()` | C + asm | défilement au pixel du monde dans le haut de l'écran (handler raster + préparation de la vue suivante) |
| panel | `panel_init(color)` / `panel_print(x, y, s)` / `panel_clear()` / `panel_done()` | asm + C | panneau de texte en bas de l'écran (jeu de caractères du système), sous la vue qui défile |

### Monde du jeu (`world`)

- **Origine** : la carte de l'utilisateur, `libc64/world/carte_monde_c64.html` (copie de `C:\Alex\C64-FCB-Map2\carte_monde_c64.html`) : 10 x 6 écrans = **400 x 150 tiles**, générés par le script de la page (graine fixe). `tools/importworld.py` exécute ce script avec `node` (seul usage de node, à relancer quand la carte change) et écrit `world/world.txt` : une valeur de case = (code de tile, Color RAM imposée ou celle du tile), 232 valeurs, puis 150 lignes de 400 index.
- **Compression** (`tools/mkworld.py`, automatique au `make`) : une case = un octet d'index ; chaque ligne codée en littéraux + jetons « répéter la case précédente N fois », coupée tous les 40 colonnes avec une table d'adresses des segments. 60 000 cases → **27 Ko** (23,7 Ko de lignes + 3,5 Ko de tables), vérifiés par un décodage complet à la génération. Lire n'importe quelle case ou ligne de la vue = partir du segment de 40 colonnes qui la contient (au plus 39 cases à sauter).
- `world_draw(x, y)` dessine la vue 40 x 25 (coin haut gauche en (x, y), ramené dans le monde : `WORLD_MAX_X` = 360, `WORLD_MAX_Y` = 125) dans l'écran `$C000` et la Color RAM : environ 3 images. `world_tile(x, y)` rend le code d'une case (0 hors du monde), pour les collisions. Constantes dans `include/world.h` (`WORLD_W`, `WORLD_H`…).
- **Défilement au pixel** : `world_scroll_init(px, py)` affiche la vue (position = coin haut gauche visible, en pixels, bornée à `WORLD_SCROLL_MAX_PX` = 2896 et `WORLD_SCROLL_MAX_PY` = 1079) et enregistre un handler raster (ligne 250, `libc64/raster`). Le programme règle la vitesse dans `world_scroll_dx` / `world_scroll_dy` (pixels par image, signés) et appelle `world_scroll_work()` dans sa boucle principale. La vue occupe les **deux tiers du haut** de l'écran : `WORLD_SCROLL_ROWS` = 16 lignes de caractères, fenêtre visible 304 x 121 pixels (38 colonnes, lignes raster 55 à 175 : les bords et la bande noire du panneau masquent les cases partiellement visibles). Le handler réécrit à chaque image `$D011`, `$D016`, `$D018` et `$D021` en entier (le panneau, plus bas, les change).
  - **Handler** (asm, ~750 cycles par image) : décalage fin (`$D016` / `$D011` bits 0-2) à chaque image ; au passage d'une case, bascule vers l'écran caché (`$D018`, écrans `$C000` / `$C400`) et copie des couleurs préparées dans la Color RAM (en avance sur le faisceau). Bord du monde : la position est bornée et `world_scroll_bumps` compte les chocs.
  - **Préparation** (`world_scroll_work`) : la vue de la case suivante (prédite selon la direction) se construit dans l'écran caché par décalage d'une case de l'écran affiché et de ses couleurs (~23 000 cycles), puis décodage de la seule ligne (~3 500) et/ou colonne (~9 000) qui apparaît. Soit 2 images environ pour un passage de case qui en laisse 8 à 1 pixel par image et 4 à 2 pixels.
  - **Diagonales** : l'axe en retard avance d'un pixel de plus par image quand cela lui permet de changer de case dans la même image que l'autre : une seule vue à préparer au lieu de deux rapprochées.
  - **Mesure du temps processeur** : `world_scroll_meter` = couleur du tour de l'écran (`$D020`) pendant chaque étape de préparation (`WORLD_SCROLL_NO_METER`, défaut : pas de mesure). Les interruptions survenues pendant une étape (dont la copie des couleurs au changement de case) sont comptées dans la bande.
  - Si la vue n'est pas prête à temps, la position attend une image (`world_scroll_stalls`) : mesuré à zéro en ligne droite et en diagonale à 1 et 2 pixels par image ; seul un départ à 1 pixel d'une case attend 2 ou 3 images (la vue n'a pas encore pu être préparée).
- Programme : `mygame/monde` (promenade au pixel, blocage aux bords).

### Panneau du bas de l'écran (`panel`)

- Sous la vue qui défile : une **bande noire** de 8 lignes raster (176-183) puis **8 lignes de texte** (184-246) dans le jeu de caractères du système, 40 colonnes, fond noir. `panel_init(color)` copie la ROM de caractères (4 Ko, les deux jeux) en RAM `$E000` (la banque VIC 3 ne voit pas la ROM ; le processeur écrit sous la ROM du KERNAL), efface le panneau (écran **`$F000`**, lignes `PANEL_ROW` = 16 à 23 ; Color RAM des mêmes lignes à `color`) et enregistre deux handlers raster. `panel_print(x, y, s)` écrit en casse normale (jeu minuscules/majuscules `$E800`, même conversion que `screen_print`).
- **Coupure au cycle près** : entre les lignes raster 48 et 175 il y a exactement 16 débuts de ligne de caractères quel que soit le décalage vertical y de la vue, donc le compteur de lignes du VIC-II arrive au panneau toujours sur la ligne 16. Handler 1 (ligne 174) : YSCROLL 6 au milieu de la ligne 175 (7 si y = 7), puis mode invalide ECM+BMM (noir) dans la bordure droite de 175 : la fin de la dernière ligne de la vue est cachée et la ligne de caractères suivante tombe dans la bande. Handler 2 (ligne 182) : `$D018` (écran `$F000`, motifs `$E800`), `$D016` (40 colonnes, sans multicolore), `$D021` noir, puis `$D011` = texte + YSCROLL 0 après la bad line 183, vers 183/61-184/4 : le panneau commence en 184. Délais par table selon y (une bad line en 174 ou 175 décale l'entrée du handler ou bloque sa boucle), réglés par mesure des cycles d'écriture dans VICE (registres `LIN`/`CYC` à un point d'arrêt sur chaque `sta`).
- Piège mesuré : si y = 0, la vue finit en 175 ; changer YSCROLL après le cycle ~57 de cette ligne fait compter une ligne de caractères de trop (panneau décalé de 8 lignes).
- Vérification : `tests/panel_test.py` (test 6), captures pour les 8 décalages : bande entièrement noire, panneau identique au pixel près, vue continue jusqu'à la ligne 175.

### Interruptions (`irq`) et lignes raster (`raster`)

- `irq` remplace le vecteur IRQ du KERNAL (`$0314`) par un répartiteur. Chaque handler est enregistré pour des sources : `IRQ_SRC_CIA` (timer du KERNAL, 60 Hz) et/ou `IRQ_SRC_VIC` (VIC-II : raster, collisions ; `irq_vic_flags` contient `$D019`). Le KERNAL continue de recevoir son interruption (clavier, horloge).
- **Tables de taille fixe** : `IRQ_MAX_HANDLERS` et `RASTER_MAX_HANDLERS`, définies dans `include/libc64.h` **et** `include/libc64_defs.inc` (même valeur, vérifiée par le test 6). Les modifier dans les deux fichiers, puis `make` : la bibliothèque est recompilée. Table pleine : la fonction d'enregistrement renvoie `0xFF`.
- **Réenregistrement** : enregistrer un handler déjà présent met à jour ses sources (irq) ou sa ligne (raster) sans prendre d'autre place. C'est permis depuis le handler lui-même (un handler raster peut se déplacer à une autre ligne, ou se retirer).
- Les handlers peuvent être écrits en C (la page zéro du runtime cc65 est sauvegardée), mais doivent rester **courts** : ils s'exécutent sous interruption.
- **Précision raster** : l'interruption est demandée `RASTER_LEAD` lignes avant la ligne voulue, puis la bibliothèque attend la ligne exacte : le handler démarre au début de sa ligne, quel que soit le délai d'entrée. Deux handlers peuvent être très proches (la bande de `mygame/demo` : 3 lignes). Le traitement du KERNAL (60 Hz) est rendu interruptible pour ne pas retarder une ligne raster. Lignes utilisables : `RASTER_LEAD` à 311 ; écran visible : 51 à 250.
- Moment d'exécution : un handler démarre vers le cycle 36 de sa ligne (sur 63), à ±3 cycles près (attente de la ligne raster) : un changement de couleur fait au début du handler tombe au milieu de la ligne affichée (« marche »). Pour un bord net, retarder l'écriture jusqu'au bord droit : 10 à 16 `NOP` (2 cycles chacun) dans le handler, 13 au milieu de la plage (voir `mygame/demo2`). Pas de « raster stable » au cycle près.
- Enchaînement de deux handlers proches : environ 100 cycles entre la fin de l'un et l'attente du suivant ; 3 lignes d'écart laissent de la marge pour des handlers courts. Un handler qui se réenregistre coûte quelques lignes : laisser de la marge avant le handler suivant.
- `irq_done()` remet le vecteur d'origine : à appeler avant de rendre la main au BASIC.

## Ajouter une fonction

1. Créer `libc64/<thème>/<nom>.c` ou `.s`, une seule fonction exportée (en asm : `.export _<nom>`).
2. Déclarer son prototype dans `include/libc64.h` et son `.import` dans `include/libc64.inc`.
3. L'appeler dans `examples/libc64_test/libtest.c` et vérifier son effet dans `tests/test_6_libc64.sh`.
4. `make` puis `make test`.

Les fonctions de la bibliothèque sont compilées avec les informations de débogage : dans VS Code, `F11` sur un appel entre dans leur source, C comme assembleur.
