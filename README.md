# C64DevEnv

Environnement de développement Commodore 64 sous WSL2 Ubuntu : assembleur et C avec **cc65**, émulation avec **VICE x64sc**, débogage scripté via le moniteur binaire. Tout est automatisé en bash, Makefile et Python 3.

## Où travailler

Tout se fait dans le dépôt, sur le système de fichiers Linux de la distribution WSL `Ubuntu-NEW` :

- depuis Ubuntu : `cd ~/C64DevEnv` (soit `/home/fenyo/C64DevEnv`) ;
- depuis Windows (Explorateur, VS Code…) : `\\wsl.localhost\Ubuntu-NEW\home\fenyo\C64DevEnv`.

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

## Arborescence

- `src/` : vos programmes (un sous-répertoire par programme, `.s` et/ou `.c`)
- `examples/` : `hello` (ca65, boucle infinie pour les tests), `hello_rts` (ca65, rend la main au BASIC : idéal pour `make run` et taper des commandes), `hello_c` (cc65)
- `tools/` : `install.sh`, `run.sh`, `stop.sh`, `dbg.py`, `mklabels.py`, `portal.py` + `portal/` + `portal.sh` (portail web)
- `tests/` : tests lancés par `make test`
- `build/` : artefacts générés (ignoré par git)
- `var/` : état du portail (PID, journal ; ignoré par git)
