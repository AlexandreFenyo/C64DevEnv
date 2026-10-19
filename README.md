# C64DevEnv

Environnement de développement Commodore 64 sous WSL2 Ubuntu : assembleur et C avec **cc65**, émulation avec **VICE x64sc**, débogage scripté via le moniteur binaire. Tout est automatisé en bash, Makefile et Python 3.

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

## Déboguer

```bash
make debug PROG=hello                     # VICE visible + moniteur binaire (port 6502)
tools/run.sh --headless --monitor hello   # même chose, invisible
tools/dbg.py screen                       # texte affiché à l'écran
tools/dbg.py regs                         # A X Y SP PC FLAGS
tools/dbg.py mem $02FF 16                 # hexdump (adresse décimale, $hex, 0xhex ou label)
tools/dbg.py break loop && tools/dbg.py cont && tools/dbg.py wait   # point d'arrêt sur un label
tools/dbg.py step ; tools/dbg.py next ; tools/dbg.py list ; tools/dbg.py delete 1
tools/dbg.py quit                         # ou tools/stop.sh
```

Les labels de `build/<prog>.labels` sont chargés dans VICE et utilisables par nom dans `dbg.py`. Détails, conventions mémoire et limites : voir `CLAUDE.md`.

## Arborescence

- `src/` : vos programmes (un sous-répertoire par programme, `.s` et/ou `.c`)
- `examples/` : `hello` (ca65) et `hello_c` (cc65)
- `tools/` : `install.sh`, `run.sh`, `stop.sh`, `dbg.py`, `mklabels.py`
- `tests/` : tests lancés par `make test`
- `build/` : artefacts générés (ignoré par git)
