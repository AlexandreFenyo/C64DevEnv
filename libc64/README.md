# libc64 : bibliothèque de fonctions C64

Fonctions réutilisables par les programmes du dépôt (`mygame/`, `src/`, `examples/`), écrites en C ou en assembleur selon les besoins (vitesse, accès matériel).

## Principe : on ne paie que ce qu'on utilise

- **Un sous-répertoire par thème** : `screen/`, `sprite/`, `input/`, `time/`, `sound/`, `random/`, `irq/`, `raster/`, `tileset/`.
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

| tileset | `tileset_install()` / `tileset_done()` | C | jeu de caractères du jeu de conduite en `$3800` + couleurs du VIC-II |
| tileset | `tile_put(x, y, code)` / `tile_put_color(x, y, code, color)` / `tile_fill(code)` / `tile_color(code)` | C | poser des tiles avec leur Color RAM par défaut ou imposée |

### Tileset du jeu (`tileset`)

- **Source unique** : `libc64/tileset/tileset.txt`, la description fournie (configuration VIC-II, palette, palettes P01-P14, 182 tiles `$40`-`$FB`, assemblages, auto-tiling de l'eau). `tools/mktileset.py` en génère `tileset/tileset_data.s` (motifs + Color RAM par défaut), `include/tiles.h` et `include/tiles.inc` (`TILE_HERBE`, `TILE_LOGO_POMME_HG`…, couleurs `TC_VERT_CLAIR`…, `TILESET_BG/MC1/MC2`). Modifier un tile : éditer `tileset.txt`, puis `make` (régénération automatique). Les fichiers générés sont versionnés ; le test 6 vérifie qu'ils sont à jour.
- `tileset_install()` copie les motifs en **`$3800`** (dernier emplacement de 2 Ko de la banque VIC 0, hors de la zone `$1000`-`$1FFF` où le VIC-II voit la ROM), met `$D021`=13, `$D022`=11, `$D023`=1, active le multicolore (`$D016` bit 4) et pointe `$D018` sur `$3800`. Elle refuse (renvoie `0xFF`) si le programme, BSS compris, déborde sur `$3800` (programme limité à environ 12 Ko ; pas de `malloc` qui monterait jusque-là).
- **Color RAM par défaut** d'un tile = couleur de sa palette : STD → couleur du bit 1 ; MC → 8 + couleur du couple `11` (le bit 3 rend la case multicolore). `tile_put_color` impose une autre valeur (convention `{tile, colorRam}` de la carte, ex. carrosserie d'une voiture : `8 + TC_BLEU`).
- **Écarts de la description, signalés par le générateur** : la Color RAM ne fournit que les couleurs 0-7. P13 (`1=ROSE`, couleur 10) est donc irréalisable : les tiles `$E4`-`$E6` (LeCat, rangée du milieu) prennent la couleur réalisable la plus proche, **VIOLET (4)**. P06 (`11=GRIS`) l'est aussi, mais ses deux tiles (`$5A`, `$5E`) n'ont aucun pixel `11` : sans effet.
- Vitrine : `examples/tileset_demo` (catalogue + assemblages).

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
