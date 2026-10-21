# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Environnement de développement Commodore 64 : cc65 (ca65/cl65) + VICE x64sc, sous WSL2 Ubuntu (WSLg pour l'affichage). Tout est scripté en bash / Makefile / Python 3 (bibliothèque standard uniquement).

## Règle n°1 : vérifier par exécution réelle

Ne jamais supposer qu'un programme marche parce qu'il compile. Après chaque modification : `make`, lancer en headless borné, lire l'écran et la mémoire avec `dbg.py`, et seulement ensuite conclure. Les tests (`make test`) doivent rester verts.

- Pour **montrer le résultat à l'utilisateur** : `make run PROG=xxx` (ou `tools/run.sh --show ...`) : fenêtre VICE visible via WSLg, laissée ouverte.
- Pour **les vérifications automatiques** (les tiennes) : toujours `--headless` (xvfb, son coupé), de préférence avec `--warp` et `--cycles N` pour une exécution bornée.

## Règle n°2 : garder le portail en phase avec les outils

Le **portail de développement** (« portail », « site web » : `tools/portal.py` + `tools/portal/`, http://localhost:8064) pilote les mêmes outils via le navigateur. Il les appelle en sous-processus : un changement de *comportement* d'un outil s'y reflète tout seul. Mais toute modification de *paramètres* doit y être reportée dans le même changement :

- option ajoutée/renommée/supprimée dans `run.sh`, `stop.sh` ou `install.sh` → registre `SCRIPT_FLAGS` de `tools/portal.py` (dans `used` avec son usage dans l'interface, ou dans `excluded` avec la raison), puis l'appel correspondant (`post_launch`, `post_capture`…) et le contrôle dans `portal/index.html` + `portal/portal.js` si l'utilisateur doit pouvoir s'en servir ;
- cible `.PHONY` du Makefile → `MAKE_TARGETS` ;
- commande de `dbg.py` → l'ajouter à `COMMANDS` **et** à la liste « Commandes » de sa docstring (format `  nom ARGS  description`, 2 espaces avant la description) : la console du portail se construit dessus ; si un bouton dédié l'utilise → `DBG_USED` ; si elle écrit un fichier → `DBG_FILE_ARG` ;
- nouvelle API ou action → test dans `tests/portal_test.py`.

Même principe pour **VS Code** : un attribut de `launch`/`attach` lu par `tools/dap.py` (`args.get("xxx")` dans `req_launch`/`req_attach`) doit être déclaré dans `configurationAttributes` de `tools/vscode/package.json` (complétion de launch.json) ; le test 5 compare les deux. Modifier `dap.py` ne demande pas de réinstaller l'extension ; modifier `tools/vscode/` demande `make vscode` puis « Developer: Reload Window ».

Vérification : `tools/portal.sh check` (ou `python3 tools/portal.py --check`), et `make test` (test 4) échoue en cas d'écart. Après modification de `portal.py`, `tools/portal.sh restart` (le JS/CSS/HTML est servi à chaud, il suffit de recharger la page).

## Commandes

```bash
tools/install.sh                 # installe/vérifie cc65, VICE (ROMs, -binarymonitor), xvfb, WSLg ; récapitulatif en fin
make                             # compile src/* et examples/* -> build/<prog>.prg + build/<prog>.labels
make list                        # programmes détectés
make run PROG=hello              # fenêtre visible (RUNFLAGS="--warp" etc. pour ajouter des options)
make debug PROG=hello            # idem + moniteur binaire (port 6502) + labels chargés
make test                        # tests/run_tests.sh (build, screenshot headless, session de débogage)
make clean                       # arrête VICE puis supprime build/
tools/stop.sh [--all]            # arrête VICE (et le démon dbg.py) ; --all tue aussi les orphelins
make portal / make portal-stop   # portail web ; tools/portal.sh start|stop|restart|status|logs|install|uninstall|check
make vscode                      # construit et installe l'extension VS Code (tools/vscode/ -> serveur VS Code de WSL)
```

Exemples : `hello` (boucle infinie `loop: jmp loop`, utilisé par les tests de point d'arrêt ; le clavier ne répond pas, normal), `hello_rts` (même affichage puis `rts` : retour au `READY.`, l'utilisateur peut taper ; à préférer pour `make run`), `hello_c` (cc65, printf, boucle infinie), `squares_c` (C pour le pas à pas : fonction, paramètre, locales, globale ; affiche `TOTAL=55` puis rend la main au BASIC), `sprite_sid` (asm commenté pour VS Code : sprite 0 en `$0340`, note 440 Hz voix 1, déplacement synchronisé sur la ligne raster 250 de x=24 à 280 en passant le bit 9 `$D010`, note relâchée après 100 images, témoin `$42` en `$02FF`, retour au BASIC ; test 5 le suit pas à pas).

Un programme = un sous-répertoire de `src/` ou `examples/` (fichiers `.s` ca65 et/ou `.c`), ou un fichier isolé `src/foo.s` / `src/foo.c`. Nom du programme = nom du répertoire/fichier. Asm pur : lié avec `c64-asm.cfg -u __EXEHDR__` (en-tête BASIC `SYS 2061`, code en `$080D`, mettre le point d'entrée en premier dans `.segment "CODE"`). Dès qu'il y a un `.c` : `c64.cfg` + runtime cc65. Compilation avec `-g` pour que les labels locaux apparaissent dans `build/<prog>.labels` (format VICE `al C:080d .start`, généré par `tools/mklabels.py` depuis `ld65 -Ln`).

Piège cc65 : les chaînes sont converties ASCII→PETSCII ; écrire le texte **en minuscules** dans le source pour qu'il s'affiche en majuscules avec le jeu de caractères par défaut du C64 (des majuscules dans le source donnent des symboles graphiques).

### run.sh

```
tools/run.sh [--show|--headless] [--warp] [--cycles N] [--screenshot f.png] [--monitor] [--load-only] [--port P] [--wait] prog.prg
```

- `--load-only` : `-autoload` au lieu de `-autostart` (même injection en RAM, « AUTOSTART: Done » aussi, mais pas de `RUN`) : le C64 est au `READY.`, le programme en mémoire ; sert à poser les points d'arrêt avant de taper `RUN` (`dap.py`).

- `--cycles N` + `--screenshot` : `-limitcycles`/`-exitscreenshot`, VICE s'arrête seul, run.sh attend. Boot + autostart ≈ 3,5 M cycles : utiliser **≥ 5 000 000** pour voir le programme à l'écran.
- `--monitor` : `-binarymonitor` (6502) + `-remotemonitor` (6510) + `-moncommands build/<prog>.labels` ; copie les labels dans `build/vice.labels` ; lance le démon `dbg.py --daemon` et attend que tout réponde.
- Sans `--cycles`/`--wait` : instance **interactive** en arrière-plan, PID dans `build/vice.pid`, log dans `build/vice.log`. Une seule instance interactive : run.sh arrête la précédente. run.sh ne rend la main qu'après la fin de l'autostart (`build/vice.state` : `starting`, écrit avant le lancement, puis `ready`) : **toute** activité sur le port du moniteur pendant l'autostart (sonde, connexion du démon, commande) peut le bloquer avant le `RUN`, de façon intermittente (constaté en mode visible). Donc run.sh ne touche au port qu'après « AUTOSTART: Done », `dbg.py` attend `ready` (et `dbg.py status` répond `starting` sans se connecter), et le portail aussi.
- `--cycles` sans `--monitor` : exécution **bornée indépendante** (n'arrête pas l'instance interactive, pas de `vice.pid`, journal `build/vice-bounded-<pid>.log` supprimé si succès). On peut donc faire des captures headless pendant que l'utilisateur garde sa fenêtre ouverte.
- Autostart = `-autostartprgmode 1` (injection directe en RAM). `VICE_EXTRA_ARGS` passe des options brutes à x64sc.

### dbg.py (client du moniteur binaire)

```
tools/dbg.py [--port P] [--labels F] [--timeout S] CMD [ARGS]
regs | mem ADDR [LEN] [--bank B] | poke ADDR VAL... | break ADDR [ADDR2] | watch ADDR [ADDR2] | delete N | list
step [N] | next | pause | jump ADDR | type TEXTE | cont | wait [S] | status | reset [hard]
dump ADDR LEN F [--bank B] | banks | disasm [ADDR|pc] [N] | where | lines [FICHIER] | segments
screen [--lower] | capture F.png [--full] | label TEXTE|ADDR | info | ping | quit
```

- Infos source : `make` produit `build/<prog>.dbg` (ld65 `--dbgfile`) ; `run.sh --monitor` le copie en `build/vice.dbg` (comme les labels). `where` → `PC=0812 examples/hello_rts/hello_rts.s:17  sta VIC_BORDERCOLOR` ; `lines`/`segments` marchent sans VICE (`--dbgfile build/x.dbg`). Pour le C, ce sont les lignes du `.c` (le `.s` intermédiaire de cc65 est supprimé).
- `disasm` : désassembleur 6502 de dbg.py (opcodes officiels), labels en opérandes, `>` = PC, `*` = point d'arrêt, lignes `          label:` ; segments non-code (RODATA, DATA, EXEHDR…) en `.byte`. Sans adresse : contexte avant le PC inclus.
- `next` sur un `JSR` : point d'arrêt (non temporaire) après l'appel puis reprise, car le « step over » de VICE s'arrête dans l'IRQ ; s'arrête sur un point d'arrêt utilisateur rencontré dans le sous-programme ; supprime son point d'arrêt dans tous les cas. Les points d'arrêt **temporaires** de VICE 3.7.1 avalent un autre arrêt survenant juste après la reprise : ne pas les utiliser.
- `jump ADDR` : place le PC (absorbe le pas « à vide » que VICE fait après un changement de PC). La pile n'est pas réinitialisée : pour relancer proprement un programme revenu au BASIC, préférer `break start` + `type run\n` + `wait`.
- `type` : clavier du C64 (lettres → majuscules PETSCII, `\n` = RETURN). Inopérant si le programme ne lit pas le clavier (boucle infinie).
- Banques (`--bank`) : `cpu` (= `default`, vue processeur), `ram` (RAM sous les ROM/E-S), `rom`, `io`, `cart`. En pas à pas, VICE ne redessine pas l'écran : `capture` montre la dernière trame, `screen` la mémoire écran actuelle.

- `capture` : image PNG de l'écran **en direct** via le moniteur (384×272 identique au pixel près à `-exitscreenshot` ; `--full` = 504×312), sans arrêter l'instance. Lire le PNG avec l'outil Read pour voir l'écran.

- Adresses : `1024`, `$0400`, `0x400`, `loop`, `loop+3`. Labels lus dans `build/vice.labels` (ou `--labels`, `$C64_LABELS`).
- Sorties stables : `A=42 X=23 Y=84 SP=f6 PC=0831 FLAGS=..-..... (20)` ; hexdump `02ff: 42 ... |B|` ; `screen` = 25 lignes `NN|...40 colonnes...|` ; `checkpoint 1 $0831 (loop) type=exec enabled=1 stop=1 hits=0` ; `stopped PC=0831 (loop) checkpoint=1` / `running` / `resumed`.
- Codes de sortie : 0 ok, 1 erreur de commande, 2 VICE absent, 3 délai (`wait` sans arrêt).
- Une commande d'inspection laisse l'émulateur dans l'état trouvé (il repart s'il tournait, reste arrêté sinon). `step`/`next` laissent arrêté ; `cont` relance ; `wait` bloque jusqu'à un point d'arrêt (ou renvoie tout de suite si déjà arrêté).
- Pourquoi un démon : VICE 3.7 relance l'exécution dès qu'un client du moniteur binaire se déconnecte, et **se fige** (moniteur GTK) si un point d'arrêt est atteint sans client connecté. `dbg.py --daemon` (socket `build/dbg.sock`, lancé par run.sh, relancé à la volée par dbg.py si absent) garde la connexion et mémorise l'état. Le moniteur texte (port 6510, `nc 127.0.0.1 6510`) reste utilisable pour des commandes VICE natives, mais il ouvre le même problème de figement : préférer dbg.py.
- run.sh rendant la main après l'autostart, le programme tourne déjà ; pour un programme qui initialise longtemps, boucler sur `mem` jusqu'à une valeur témoin.

### Portail (tools/portal.py)

- Serveur `http.server` (bibliothèque standard) sur 127.0.0.1:8064, joignable depuis Windows via `localhost`. Démarrage : `make portal` (processus, `var/portal.pid`, `var/portal.log` : hors de `build/` que `make clean` efface) ou service systemd utilisateur `c64-portal` (`tools/portal.sh install`, démarre à l'ouverture de la distribution, `KillMode=process` pour que VICE survive à un redémarrage du portail).
- Programmes (Lancer avec mode/moniteur/warp, Capture bornée, Sources, `.prg`), opérations longues en tâches (une à la fois : build, tests, nettoyage, vérification d'installation), moniteur (image en direct, écran texte, registres, Recommencer pas à pas / Pause / Pas / Pas sans JSR / Continuer, vue **Code** désassemblage + source avec ligne courante et points d'arrêt d'un clic, points d'arrêt, labels, clavier du C64, console dbg.py générique), carte **Mémoire** (64 Ko en image, focus hexa + codes écran/PETSCII/ASCII, sélection à la souris avec valeurs/mots/texte, surveillance, édition par double-clic, octets modifiés surlignés, banques), journaux, page de cohérence.
- Liens directs : `http://localhost:8064/#mem=0400-04ff` (zone mémoire sélectionnée), `#code=source` ou `#code=disasm` : utile pour montrer quelque chose à l'utilisateur.
- « Recommencer pas à pas » : si le PC est en ROM (programme revenu au BASIC), point d'arrêt sur le point d'entrée (début de STARTUP/CODE, `$080D`) + `RUN` tapé ; sinon `jump` au point d'entrée.
- L'état est partagé par fichiers (`build/vice.pid`, `vice.state`, `dbg.sock`) : ce que je lance en ligne de commande apparaît dans le portail et inversement. Le démon dbg.py sert les clients à tour de rôle (file d'attente).
- API JSON sous `/api/*` (POST exigent `Content-Type: application/json` ; Host/Origin non locaux refusés). Utile pour moi aussi : `curl -s localhost:8064/api/status`.

### VS Code (tools/dap.py + tools/vscode/)

- `tools/dap.py` : adaptateur Debug Adapter Protocol (stdin/stdout), bibliothèque standard, importe `dbg.py` (Monitor, DebugInfo, Labels, désassembleur). Il passe par le **démon** dbg.py comme tout le monde : VS Code, le portail et `dbg.py` en ligne de commande voient la même instance et les mêmes arrêts (un arrêt provoqué ailleurs apparaît dans VS Code en « pause », une reprise ailleurs en « continued »). Journal : `build/dap.log`.
- `tools/vscode/` : extension minimale (`c64devenv.c64-vice`, `extensionKind: workspace`) : type de débogage `c64` qui lance `python3 <dossier ouvert>/tools/dap.py`, langage `ca65` (coloration, points d'arrêt autorisés dans les `.s`), complétion de launch.json. `tools/vscode-install.sh` (= `make vscode`) fabrique le `.vsix` (zip construit en Python, pas de npm) et l'installe avec `~/.vscode-server/bin/*/bin/code-server --install-extension` (le `code` de WSL hors terminal VS Code est celui de Windows : il installerait côté Windows). `.vscode/launch.json`, `tasks.json` (make + problemMatcher cc65/ca65), `settings.json` (`*.s` → ca65, la kickass-c64 de l'utilisateur réclame aussi les `.s`) sont versionnés.
- `launch` : `make` (attribut `build`), `run.sh --show|--headless --monitor --load-only`, réponse + `initialized`, VS Code envoie les points d'arrêt, puis `configurationDone` tape `RUN` ; `stopOnEntry` = point d'arrêt sur `_main` (C) ou début de STARTUP/CODE (asm). Fin de session : `stop.sh` (VICE fermé). `attach` : labels/infos de `build/vice.*`, fin de session = nos points d'arrêt retirés + VICE relancé.
- Pas à pas = générateurs Python : `yield` = VICE relancé, la boucle de surveillance (état du démon toutes les 0,15 s, sans toucher à VICE) reprend le générateur à l'arrêt ; un arrêt proche (retour de JSR) est attendu sur place (`QUICK_WAIT`). Instruction : `advance 1` ; si le PC obtenu n'est pas un successeur possible, une IRQ/NMI a été prise : on retrouve l'adresse de retour dans la pile et on y court (on ne s'arrête jamais dans l'IRQ). JSR franchi = point d'arrêt après le JSR + vérification de SP (récursion). Ligne = instructions jusqu'à une autre ligne ; JSR vers du code sans source (ROM, runtime cc65) franchis ; `jmp incsp2` & co. (épilogues cc65) : course jusqu'au retour ; au-delà de 500 instructions sur la même ligne (boucle) : points d'arrêt sur toutes les autres lignes + adresse de retour. stepOut : adresse de retour de la pile d'appels.
- Pile d'appels : heuristique sur la pile 6502 (mots dont l'adresse+1-3 est un `JSR`), jusqu'au premier appelant en ROM (BASIC). Fonctions C : portées `scope` du `.dbg` ; asm : label de code le plus proche.
- Variables C : cc65 2.19 n'écrit **pas** les types dans le `.dbg` (tous `type=0`) ni les globales dans `csym` : types déduits de la déclaration dans le `.c` (regex), tailles par écart entre décalages/labels ; globales = symboles `_xxx` des segments DATA/BSS des modules du programme. Locales : `csym sc=auto offs=N`, adresse = `sp` (zp `$02`) + taille des locales + offs, valable aux débuts de ligne (pas au milieu d'une expression qui empile) et après le prologue (`jsr pushax` / `jsr decspN`), signalé sinon.
- Puces du C64 (groupes repliés, lus à l'ouverture) : « Mémoire ($01, vecteurs) » (ROM/RAM/E-S visibles selon $01, banque VIC, vecteurs IRQ/BRK/NMI), « VIC-II » (mode, écran affiché, adresses écran/charset/bitmap calculées avec $D018 + banque CIA 2, couleurs nommées, raster, IRQ raster, défilement, 38/40 colonnes), « Sprites » (8, position 9 bits, couleur, multicolore, agrandissement, priorité, pointeur -> adresse des données, collisions), « SID » (voix : fréquence en Hz PAL, forme d'onde, gate, ADSR ; volume, filtre ; registres en écriture seule : VICE renvoie la dernière valeur écrite), « CIA 1/2 » (ports, timers, TOD, ICR). Lecture dans la banque `io` de VICE (sans effet de bord, même si $01 masque les E/S) ; chaque puce a ses « registres bruts » modifiables. Idée reprise de l'extension VS64 (comparatif fait le 2026-10-21 : VS64 bon sur les puces mais faible en C ; VS65/cc65-vice ne s'arrête jamais sur un point d'arrêt ici, même avec VICE 3.8).
- Console de débogage : toute commande `dbg.py` (exécutée dans le processus, sortie capturée) ; sinon expression : variable C, label, équivalence (`= $d020 ; [$d020] = $fe`), `$adresse`, registre, avec `,b` `,w` `,l` `,s` `,N`. Points d'arrêt : lignes (déplacés sur la 1re ligne de code suivante, une par plage si la ligne C est en plusieurs morceaux), fonctions/labels, instructions (vue Désassemblage), données (lecture/écriture : checkpoints load/store). `readMemory`/`writeMemory`, `gotoTargets` (Set Next Statement), `setVariable` (registres, drapeaux, mémoire).
- Vérification : `tests/dap_test.py` (test 5) joue VS Code. Vérification dans un **vrai** VS Code (faite une fois, à refaire si l'extension change) : télécharger `https://update.code.visualstudio.com/latest/linux-x64/stable` dans le scratchpad, puis `xvfb-run -a env -u WAYLAND_DISPLAY VSCode-linux-x64/code --no-sandbox --disable-gpu --user-data-dir X --extensions-dir Y --extensionDevelopmentPath=tools/vscode --extensionTestsPath=<dossier avec index.js exportant run()> ~/C64DevEnv` ; `run()` utilise `vscode.debug.startDebugging`, `registerDebugAdapterTrackerFactory`, `executeCommand('workbench.action.debug.stepOver')`… Le tracker voit une « read error » à chaque fin de session : VS Code tue l'adaptateur après `disconnect`, sans conséquence.

## Boucle de travail recommandée

1. `make` (zéro warning).
2. `tools/run.sh --headless --warp --cycles 5000000 --screenshot build/x.png build/x.prg` puis regarder le PNG (outil Read) ; ou
3. `tools/run.sh --headless --warp --monitor build/x.prg` puis `dbg.py screen`, `dbg.py mem ...`, `dbg.py break label` / `cont` / `wait` / `regs` / `step`.
4. Corriger, `tools/stop.sh`, recommencer. `make test` avant de conclure.
5. Pour montrer : `make run PROG=x` (visible), laisser la fenêtre ouverte.

Les tests `tests/test_*.sh` sont des exemples complets de session automatisée (test 3 = débogage de bout en bout, test 4 = portail + cohérence, test 5 = VS Code/DAP + cohérence extension). `make test` arrête l'instance VICE de l'utilisateur (tests 3 et 4 utilisent le moniteur) : le prévenir et la relancer ensuite.

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

- `--show` exige un WSLg fonctionnel ; `install.sh` le diagnostique (si weston redémarre en boucle, `wsl --shutdown` côté Windows). Sur ce poste la boucle revient parfois même après `wsl --shutdown` (constaté le 2026-10-21) : `run.sh --show` teste d'abord l'affichage (`xdpyinfo`, 3 s) et échoue avec un message clair (mode invisible + image du portail) au lieu de l'erreur GTK « cannot open display ». Le headless ne dépend pas de WSLg.
- Le paquet Ubuntu de VICE n'inclut pas les ROMs : `install.sh` les récupère depuis les sources officielles dans `~/.local/share/vice/C64` (ou compile VICE si la version est < 3.5).
- `dbg.py` sert un client à la fois (les suivants attendent leur tour) ; `screen` suppose l'écran en `$0400` sauf argument.
- VICE 3.7.1 envoie la réponse « display get » avec 4 octets de pixels en moins (coin inférieur droit, hors zone recadrée) : `dbg.py` complète.
- `tools/stop.sh --all` ne tue que les processus `x64sc` et les `xvfb-run` qui lancent x64sc (plus de `pkill -f`, qui tuait aussi le shell appelant quand sa ligne de commande contenait « xvfb-run -a … x64sc »).
- Le portail n'a pas d'authentification : il n'écoute que sur 127.0.0.1 (ne pas changer `PORTAL_HOST`).
