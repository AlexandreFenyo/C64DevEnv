# libc64 : bibliothèque de fonctions C64

Fonctions réutilisables par les programmes du dépôt (`mygame/`, `src/`, `examples/`), écrites en C ou en assembleur selon les besoins (vitesse, accès matériel).

## Principe : on ne paie que ce qu'on utilise

- **Un sous-répertoire par thème** : `screen/`, `sprite/`, `input/`, `time/`, `sound/`, `random/`.
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

## Ajouter une fonction

1. Créer `libc64/<thème>/<nom>.c` ou `.s`, une seule fonction exportée (en asm : `.export _<nom>`).
2. Déclarer son prototype dans `include/libc64.h` et son `.import` dans `include/libc64.inc`.
3. L'appeler dans `examples/libc64_test/libtest.c` et vérifier son effet dans `tests/test_6_libc64.sh`.
4. `make` puis `make test`.

Les fonctions de la bibliothèque sont compilées avec les informations de débogage : dans VS Code, `F11` sur un appel entre dans leur source, C comme assembleur.
