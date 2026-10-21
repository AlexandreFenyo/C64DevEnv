# mygame : versions du jeu

Chaque sous-répertoire est une version du jeu, donc un programme : `mygame/demo/` donne `build/demo.prg` (`make run PROG=demo`). Deux programmes du dépôt ne peuvent pas porter le même nom : `make` le signale.

Une version utilise les fonctions de `libc64/` (`#include "libc64.h"`). Seules celles qu'elle appelle sont incorporées à son `.prg` (voir `libc64/README.md`).

- `demo/` : un vaisseau piloté à la manette du port 2, un son sur le bouton de tir.

Pour jouer avec le clavier : dans la fenêtre VICE, menu *Preferences → Settings → Input devices → Joystick*, port 2 sur « Keyset A » ou « Numpad ».
