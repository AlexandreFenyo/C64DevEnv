# C64DevEnv

Environnement de développement Commodore 64 sous WSL2 Ubuntu : assembleur et C avec **cc65**, émulation avec **VICE x64sc**, débogage scripté via le moniteur binaire. Tout est automatisé en bash, Makefile et Python 3.

## Où travailler

Tout se fait dans le dépôt, sur le système de fichiers Linux de la distribution WSL `Ubuntu-NEW` :

- depuis Ubuntu : `cd ~/C64DevEnv` (soit `/home/fenyo/C64DevEnv`) ;
- depuis Windows (Explorateur, VS Code…) : `\\wsl.localhost\Ubuntu-NEW\home\fenyo\C64DevEnv`.

Après un `wsl --shutdown`, ouvrez d'abord Ubuntu depuis le bureau Windows (Terminal ou menu Démarrer) avant de relancer Claude Code : si WSL est redémarré par un processus d'arrière-plan, les fenêtres VICE s'ouvrent dans une session Windows invisible.

Toutes les commandes ci-dessous se lancent depuis ce répertoire, dans un shell Ubuntu. Les fichiers générés vont dans `build/`.

## Installation

```bash
tools/install.sh
```

Installe les paquets (cc65, vice, xvfb, imagemagick…), récupère les ROMs C64 absentes du paquet Ubuntu, vérifie `-binarymonitor` et WSLg, puis affiche un récapitulatif.

## Les trois commandes essentielles

```bash
make                      # compile src/ et examples/ -> build/*.prg (+ labels VICE)
make run PROG=hello       # lance le programme dans une fenêtre VICE (WSLg)
make test                 # build + exécution headless + session de débogage automatisée
```

Pour une exécution invisible et bornée avec capture d'écran :

```bash
tools/run.sh --headless --warp --cycles 5000000 --screenshot build/hello.png build/hello.prg
```

## Portail de développement (navigateur)

**URL : http://localhost:8064**, à ouvrir dans le navigateur Windows (ou `http://127.0.0.1:8064` depuis Ubuntu).

Sur ce poste, le portail est installé comme service : il démarre tout seul à chaque ouverture d'Ubuntu, il suffit d'ouvrir l'URL. Pour le démarrer ou le gérer à la main (depuis `~/C64DevEnv`) :

```bash
tools/portal.sh status    # en service ? affiche l'URL
tools/portal.sh start     # démarre le portail (équivalent : make portal)
tools/portal.sh stop      # l'arrête (équivalent : make portal-stop)
tools/portal.sh restart   # après une modification de tools/portal.py
tools/portal.sh install   # l'installe en service permanent (uninstall pour l'enlever)
```

Depuis la page : compiler, lancer un programme (visible ou invisible, avec ou sans moniteur, warp), faire une capture d'écran, lire les sources, lancer les tests, et déboguer :

- **Moniteur** : image du C64 en direct, registres, « Recommencer pas à pas » (arrêt sur la première instruction du programme), Pause, Pas, Pas sans JSR, Continuer, points d'arrêt, labels, clavier du C64.
- **Code** : désassemblage ou source (`.s` / `.c`) avec la ligne en cours surlignée ; un clic dans la marge pose ou retire un point d'arrêt.
- **Mémoire** : carte visuelle des 64 Ko (un pixel par octet, octets modifiés en blanc), focus hexa + texte (codes écran, PETSCII, ASCII) sur la zone cliquée, sélection à la souris (valeurs, mots 16 bits, texte, copie, surveillance), modification d'un octet par double-clic, raccourcis vers les zones du C64 et les segments du programme.

Lien direct vers une zone mémoire : `http://localhost:8064/#mem=0400-04ff`. Le portail appelle les mêmes outils que la ligne de commande.

## Déboguer

```bash
make debug PROG=hello                     # VICE visible + moniteur binaire (port 6502)
tools/run.sh --headless --monitor hello   # même chose, invisible
tools/dbg.py screen                       # texte affiché à l'écran
tools/dbg.py capture build/ecran.png      # image de l'écran, sans arrêter le programme
tools/dbg.py regs                         # A X Y SP PC FLAGS
tools/dbg.py mem $02FF 16                 # hexdump (adresse décimale, $hex, 0xhex ou label)
tools/dbg.py break loop && tools/dbg.py cont && tools/dbg.py wait   # point d'arrêt sur un label
tools/dbg.py step ; tools/dbg.py next ; tools/dbg.py list ; tools/dbg.py delete 1
tools/dbg.py where                        # ligne source de l'instruction courante
tools/dbg.py disasm                       # désassemblage autour du PC, avec labels
tools/dbg.py type 'run\n'                 # tape au clavier du C64
tools/dbg.py quit                         # ou tools/stop.sh
```

Les labels de `build/<prog>.labels` sont chargés dans VICE et utilisables par nom dans `dbg.py`. Détails, conventions mémoire et limites : voir `CLAUDE.md`.

## Déboguer dans VS Code (asm et C)

Une fois : `make vscode` (installe l'extension du dépôt dans VS Code côté WSL, y compris dans votre profil VS Code `C64`). Ensuite, pour travailler : **`make code`** (ou `code --profile C64 ~/C64DevEnv`) ouvre VS Code sous Windows, connecté à WSL (« WSL: Ubuntu-NEW » en bas à gauche), dans le profil `C64` qui regroupe les extensions de développement C64. Si VS Code était déjà ouvert : `Ctrl+Shift+P` → « Developer: Reload Window ». À la première ouverture, acceptez de faire confiance au dossier (« Trust »), sinon `F5` et les tâches sont bloqués. La complétion C connaît les en-têtes cc65 (`.vscode/c_cpp_properties.json`).

1. Ouvrez un `.s` ou un `.c` de `src/` ou `examples/` (ex. `examples/squares_c/squares.c`).
2. `F9` (ou clic dans la marge) pose un point d'arrêt.
3. `F5` : compile, ouvre VICE et s'arrête au début (`main` en C, première instruction en asm). Les configurations sont dans `.vscode/launch.json` (VICE visible, invisible + warp, jusqu'au premier point d'arrêt, s'attacher à un VICE déjà lancé).
4. `F10` ligne suivante, `F11` entrer dans la fonction (les appels ROM ou bibliothèque cc65 sont franchis d'un bloc), `Maj+F11` sortir, `F5` continuer, `Maj+F5` arrêter (ferme VICE).

Panneau Variables : registres (modifiables), locales et globales C avec leur type, données du programme asm, pile 6502, écran texte, et l'état des puces du C64 à chaque pas : configuration mémoire ($01, vecteurs d'interruption), VIC-II (mode, adresses écran et caractères, couleurs, raster), 8 sprites, SID (fréquence en Hz, forme d'onde, ADSR des 3 voix), CIA 1 et 2 (timers, ports) ; chaque puce a aussi ses registres bruts, modifiables. Survol d'un nom dans le source : sa valeur (`VIC_BORDERCOLOR` → `$d020 → $fe`). Espions : `total`, `message,s` (chaîne), `$0400,40` (40 octets), `ptr,w` (mot). Console de débogage : toutes les commandes de `dbg.py` (`regs`, `mem $0400 32`, `screen`, `disasm`…). Clic droit → « Open Disassembly View » pour le pas à pas instruction par instruction. Un clic droit sur une variable propose un point d'arrêt sur sa modification.

Pour déboguer une instance lancée par `make debug PROG=xxx` ou par le portail (case Moniteur) : configuration « C64 : s'attacher à VICE ». Le portail, `dbg.py` et VS Code pilotent la même instance en même temps.

## Bibliothèque libc64 et jeu (mygame)

- `libc64/` : fonctions réutilisables en C et en assembleur (écran, sprites, manette, son, temps, hasard), une par fichier. `#include "libc64.h"` suffit : un programme n'embarque que les fonctions qu'il appelle. Détails et liste : `libc64/README.md`.
- `mygame/` : les versions du jeu, une par sous-répertoire ; la première est `mygame/demo` (`make run PROG=demo`, ou `F5` dans VS Code sur `mygame/demo/main.c`).

## Arborescence

- `src/` : vos programmes (un sous-répertoire par programme, `.s` et/ou `.c`)
- `libc64/` : bibliothèque de fonctions C64 (C et asm)
- `mygame/` : versions du jeu (`demo/`…)
- `examples/` : `hello` (ca65, boucle infinie pour les tests), `hello_rts` (ca65, rend la main au BASIC : idéal pour `make run` et taper des commandes), `hello_c` (cc65), `squares_c` (cc65, pour le pas à pas : fonction, locales, globales), `sprite_sid` (ca65, à suivre dans VS Code : un sprite et une note SID, l'effet de chaque bloc visible dans les groupes VIC-II, Sprites et SID)
- `tools/` : `install.sh`, `run.sh`, `stop.sh`, `dbg.py`, `mklabels.py`, `portal.py` + `portal/` + `portal.sh` (portail web), `dap.py` + `vscode/` + `vscode-install.sh` (débogage VS Code)
- `.vscode/` : configurations de débogage et tâches (make) pour VS Code
- `tests/` : tests lancés par `make test`
- `build/` : artefacts générés (ignoré par git)
- `var/` : état du portail (PID, journal ; ignoré par git)
