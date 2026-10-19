# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Environnement de développement Commodore 64 : cc65 (ca65/cl65) + VICE x64sc, sous WSL2 Ubuntu (WSLg pour l'affichage). Tout est scripté en bash / Makefile / Python 3 (bibliothèque standard uniquement).

## Règle n°1 : vérifier par exécution réelle

Ne jamais supposer qu'un programme marche parce qu'il compile. Après chaque modification : `make`, lancer en headless borné, lire l'écran et la mémoire avec `dbg.py`, et seulement ensuite conclure. Les tests (`make test`) doivent rester verts.

- Pour **montrer le résultat à l'utilisateur** : `make run PROG=xxx` (ou `tools/run.sh --show ...`) : fenêtre VICE visible via WSLg, laissée ouverte.
- Pour **les vérifications automatiques** (les tiennes) : toujours `--headless` (xvfb, son coupé), de préférence avec `--warp` et `--cycles N` pour une exécution bornée.

## Commandes

```bash
tools/install.sh                 # installe/vérifie cc65, VICE (ROMs, -binarymonitor), xvfb, WSLg ; récapitulatif en fin
make                             # compile src/* et examples/* -> build/<prog>.prg + build/<prog>.labels
make list                        # programmes détectés
make run PROG=hello              # fenêtre visible (RUNFLAGS="--warp" etc. pour ajouter des options)
make debug PROG=hello            # idem + moniteur binaire (port 6502) + labels chargés
make test                        # tests/run_tests.sh (build, screenshot headless, session de débogage)
make clean
tools/stop.sh [--all]            # arrête VICE (et le démon dbg.py) ; --all tue aussi les orphelins
```

Exemples : `hello` (boucle infinie `loop: jmp loop`, utilisé par les tests de point d'arrêt ; le clavier ne répond pas, normal), `hello_rts` (même affichage puis `rts` : retour au `READY.`, l'utilisateur peut taper ; à préférer pour `make run`), `hello_c` (cc65, printf).

Un programme = un sous-répertoire de `src/` ou `examples/` (fichiers `.s` ca65 et/ou `.c`), ou un fichier isolé `src/foo.s` / `src/foo.c`. Nom du programme = nom du répertoire/fichier. Asm pur : lié avec `c64-asm.cfg -u __EXEHDR__` (en-tête BASIC `SYS 2061`, code en `$080D`, mettre le point d'entrée en premier dans `.segment "CODE"`). Dès qu'il y a un `.c` : `c64.cfg` + runtime cc65. Compilation avec `-g` pour que les labels locaux apparaissent dans `build/<prog>.labels` (format VICE `al C:080d .start`, généré par `tools/mklabels.py` depuis `ld65 -Ln`).

Piège cc65 : les chaînes sont converties ASCII→PETSCII ; écrire le texte **en minuscules** dans le source pour qu'il s'affiche en majuscules avec le jeu de caractères par défaut du C64 (des majuscules dans le source donnent des symboles graphiques).

### run.sh

```
tools/run.sh [--show|--headless] [--warp] [--cycles N] [--screenshot f.png] [--monitor] [--port P] [--wait] prog.prg
```

- `--cycles N` + `--screenshot` : `-limitcycles`/`-exitscreenshot`, VICE s'arrête seul, run.sh attend. Boot + autostart ≈ 3,5 M cycles : utiliser **≥ 5 000 000** pour voir le programme à l'écran.
- `--monitor` : `-binarymonitor` (6502) + `-remotemonitor` (6510) + `-moncommands build/<prog>.labels` ; copie les labels dans `build/vice.labels` ; lance le démon `dbg.py --daemon` et attend que tout réponde.
- Sans `--cycles`/`--wait` : VICE tourne en arrière-plan, PID dans `build/vice.pid`, log dans `build/vice.log`. Une seule instance : run.sh arrête la précédente.
- Autostart = `-autostartprgmode 1` (injection directe en RAM). `VICE_EXTRA_ARGS` passe des options brutes à x64sc.

### dbg.py (client du moniteur binaire)

```
tools/dbg.py [--port P] [--labels F] [--timeout S] CMD [ARGS]
regs | mem ADDR [LEN] | poke ADDR VAL... | break ADDR [ADDR2] | watch ADDR [ADDR2] | delete N | list
step [N] | next | cont | wait [S] | status | reset [hard] | dump ADDR LEN FICHIER | screen [--lower]
label TEXTE|ADDR | info | quit
```

- Adresses : `1024`, `$0400`, `0x400`, `loop`, `loop+3`. Labels lus dans `build/vice.labels` (ou `--labels`, `$C64_LABELS`).
- Sorties stables : `A=42 X=23 Y=84 SP=f6 PC=0831 FLAGS=..-..... (20)` ; hexdump `02ff: 42 ... |B|` ; `screen` = 25 lignes `NN|...40 colonnes...|` ; `checkpoint 1 $0831 (loop) type=exec enabled=1 stop=1 hits=0` ; `stopped PC=0831 (loop) checkpoint=1` / `running` / `resumed`.
- Codes de sortie : 0 ok, 1 erreur de commande, 2 VICE absent, 3 délai (`wait` sans arrêt).
- Une commande d'inspection laisse l'émulateur dans l'état trouvé (il repart s'il tournait, reste arrêté sinon). `step`/`next` laissent arrêté ; `cont` relance ; `wait` bloque jusqu'à un point d'arrêt (ou renvoie tout de suite si déjà arrêté).
- Pourquoi un démon : VICE 3.7 relance l'exécution dès qu'un client du moniteur binaire se déconnecte, et **se fige** (moniteur GTK) si un point d'arrêt est atteint sans client connecté. `dbg.py --daemon` (socket `build/dbg.sock`, lancé par run.sh, relancé à la volée par dbg.py si absent) garde la connexion et mémorise l'état. Le moniteur texte (port 6510, `nc 127.0.0.1 6510`) reste utilisable pour des commandes VICE natives, mais il ouvre le même problème de figement : préférer dbg.py.
- Juste après l'autostart, attendre que le programme soit lancé (boucler sur `mem` jusqu'à la valeur témoin, ~1 s en warp) avant d'inspecter.

## Boucle de travail recommandée

1. `make` (zéro warning).
2. `tools/run.sh --headless --warp --cycles 5000000 --screenshot build/x.png build/x.prg` puis regarder le PNG (outil Read) ; ou
3. `tools/run.sh --headless --warp --monitor build/x.prg` puis `dbg.py screen`, `dbg.py mem ...`, `dbg.py break label` / `cont` / `wait` / `regs` / `step`.
4. Corriger, `tools/stop.sh`, recommencer. `make test` avant de conclure.
5. Pour montrer : `make run PROG=x` (visible), laisser la fenêtre ouverte.

Les tests `tests/test_*.sh` sont des exemples complets de session automatisée (test 3 = débogage de bout en bout).

## Mémoire C64 utile

| Zone | Adresse | Rôle |
|---|---|---|
| Zero page | `$00-$FF` | `$01` = banking (ROM/IO), `$FB-$FE` libres pour l'asm (`FREKZP`), cc65 utilise `$02-$1A` (sp, ptr1..4, tmp1..4, regsave) |
| Pile | `$0100-$01FF` | |
| Témoins/scratch | `$02FE-$02FF` | utilisés par les exemples (`hello` écrit `$42` en `$02FF`, `hello_c` `$43` en `$02FE`) |
| Vecteurs | `$0314` IRQ, `$0316` BRK, `$0318` NMI | |
| Écran texte | `$0400-$07E7` | 1000 codes écran (pas PETSCII : `A`=1, espace=32, `@`=0) ; `$0288` = page écran |
| Couleur courante | `$0286` | couleur du texte KERNAL |
| Programme BASIC | `$0801` | en-tête `SYS 2061`, code en `$080D` |
| VIC-II | `$D000-$D02E` | `$D011` ctrl1 (bit 4 = écran on), `$D012` raster, `$D016` ctrl2, `$D018` mémoire vidéo/charset, `$D019`/`$D01A` IRQ, `$D020` bordure, `$D021` fond, `$D015` sprites on, `$D027+` couleurs sprites |
| SID | `$D400-$D41C` | voix 1 `$D400` (freq lo/hi, PW, `$D404` ctrl, `$D405` AD, `$D406` SR), voix 2 `$D407`, voix 3 `$D40E`, `$D418` volume |
| Color RAM | `$D800-$DBE7` | 1 nibble par cellule |
| CIA1 | `$DC00` | clavier/joystick, timers, IRQ (`$DC0D`) |
| CIA2 | `$DD00` | banque VIC (bits 0-1), NMI (`$DD0D`) |
| KERNAL | `$FFD2` CHROUT, `$FFE4` GETIN, `$FFCF` CHRIN, `$E544` clear screen | |

Couleurs : 0 noir, 1 blanc, 2 rouge, 3 cyan, 4 violet, 5 vert, 6 bleu, 7 jaune, 8 orange, 9 marron, 10 rose, 11 gris foncé, 12 gris, 13 vert clair, 14 bleu clair, 15 gris clair. `c64.inc` (cc65) fournit les symboles `VIC_*`, `SID_*`, `CIA1_*`, visibles dans les labels.

## Limites connues

- `--show` exige un WSLg fonctionnel ; `install.sh` le diagnostique (si weston redémarre en boucle, `wsl --shutdown` côté Windows). Le headless ne dépend pas de WSLg.
- Le paquet Ubuntu de VICE n'inclut pas les ROMs : `install.sh` les récupère depuis les sources officielles dans `~/.local/share/vice/C64` (ou compile VICE si la version est < 3.5).
- `dbg.py` ne gère qu'un client à la fois (les suivants attendent) ; `screen` suppose l'écran en `$0400` sauf argument.
