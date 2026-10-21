# mygame : versions du jeu

Chaque sous-répertoire est une version du jeu, donc un programme : `mygame/demo/` donne `build/demo.prg` (`make run PROG=demo`). Deux programmes du dépôt ne peuvent pas porter le même nom : `make` le signale.

Une version utilise les fonctions de `libc64/` (`#include "libc64.h"`). Seules celles qu'elle appelle sont incorporées à son `.prg` (voir `libc64/README.md`).

- `demo/` : un vaisseau piloté à la manette du port 2, un son sur le bouton de tir, une bande bleue de 3 lignes raster au milieu de l'écran (`libc64/raster`).
- `monde/` : promenade dans le monde du jeu (400 x 150 tiles, `libc64/world`) : défilement au pixel, en continu, à la manette (port 2) ou au clavier (flèches, ou W A S D, maintenues) : 1 pixel par image, 2 avec le bouton de tir ou la barre d'espace ; la vue s'arrête aux bords du monde. Mesure du temps processeur : le tour de l'écran passe au blanc pendant la préparation de la vue suivante (écran caché du double tampon) ; hauteur des bandes blanches = part de l'image occupée ; touche M pour l'activer ou la couper.
- `demo2/` : comme `demo`, mais le début de la bande est retardé par 13 `NOP` dans son handler, pour que la couleur change dans le bord droit de l'écran plutôt qu'au milieu de la ligne : bord haut sans « marche ». La fin de bande n'est pas retardée (sa marche reste visible, pour comparer).

Pour jouer avec le clavier : dans la fenêtre VICE, menu *Preferences → Settings → Input devices → Joystick*, port 2 sur « Keyset A » ou « Numpad ».
