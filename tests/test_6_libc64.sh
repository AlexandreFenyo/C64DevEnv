#!/usr/bin/env bash
# Test 6 : bibliothèque libc64 et premier programme de mygame/.
#   - build/libc64.lib contient un module par fichier de libc64/ ;
#   - demo n'incorpore que les modules qu'il appelle (rnd8, sprite_hide absents) ;
#   - examples/libc64_test appelle toutes les fonctions : résultats vérifiés en mémoire ;
#   - irq / raster : réenregistrement, tables pleines, désenregistrement,
#     handlers appelés exactement à leur ligne (y compris déplacés depuis un
#     handler) ; constantes identiques en C (libc64.h) et en asm (libc64_defs.inc) ;
#   - demo tourne : texte, sprite, position x sur 9 bits, bande de 3 lignes.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
D=tools/dbg.py
fail() { echo "ECHEC : $*"; exit 1; }
trap 'tools/stop.sh --quiet' EXIT

make >/dev/null || fail "make"
for c in IRQ_MAX_HANDLERS IRQ_SRC_CIA IRQ_SRC_VIC RASTER_MAX_HANDLERS RASTER_LEAD WORLD_SCROLL_ROWS WORLD_SCROLL_VIEW_H PANEL_ROW PANEL_ROWS; do
    h=$(awk -v c="$c" '$1 == "#define" && $2 == c { print $3 }' libc64/include/libc64.h)
    a=$(awk -v c="$c" '$1 == c && $2 == "=" { print $3 }' libc64/include/libc64_defs.inc)
    [ -n "$h" ] && [ $((h)) = $((${a/\$/0x})) ] || fail "constante $c : libc64.h=$h, libc64_defs.inc=$a"
done
echo "ok : constantes identiques en C et en asm"
nsrc=$(ls libc64/*/*.c libc64/*/*.s | wc -l)
nmod=$(ar65 t build/libc64.lib | grep -c '\.o$')
[ "$nsrc" = "$nmod" ] || fail "libc64.lib : $nmod modules pour $nsrc sources"
echo "ok : build/libc64.lib, $nmod modules"

mods=$(awk '/^Modules list:/,/^Segment list:/' build/demo.map | grep -o 'libc64.lib([a-z0-9_]*\.o)' | sort -u)
echo "$mods" | grep -q 'sprite_move' || fail "demo : sprite_move absent de l'édition de liens"
for m in rnd8 sprite_hide; do
    echo "$mods" | grep -q "($m.o)" && fail "demo : $m incorporé alors qu'il n'est pas appelé"
done
echo "ok : demo n'incorpore que $(echo "$mods" | wc -l) modules de libc64 (ni rnd8 ni sprite_hide)"

# Toutes les fonctions, en exécution réelle.
tools/run.sh --headless --warp --monitor build/libc64_test.prg >/dev/null || fail "run.sh libc64_test"
for _ in $(seq 1 50); do
    [ "$($D mem _test_done 1 | cut -c7-8)" = 01 ] && break
    sleep 0.2
done
[ "$($D mem _test_done 1 | cut -c7-8)" = 01 ] || fail "libc64_test ne termine pas"
val() { $D mem "$1" "${2:-1}" | cut -c7-$((6 + 3 * ${2:-1} - 1)); }
[ "$(val _spr_after_show)" = 08 ] || fail "sprite_show : \$D015 = $(val _spr_after_show), attendu 08"
[ "$(val _spr_after_hide)" = 00 ] || fail "sprite_hide : \$D015 = $(val _spr_after_hide), attendu 00"
[ "$(val _hi_after_move)" = 08 ] || fail "sprite_move x=300 : \$D010 = $(val _hi_after_move), attendu 08"
[ "$($D mem '$d006' 2 --bank io | cut -c7-11)" = "2c 64" ] || fail "sprite_move : x bas/y du sprite 3"
[ "$($D mem '$07fb' 1 | cut -c7-8)" = 0e ] || fail "sprite_load : pointeur du sprite 3"
[ "$($D mem '$0380' 3 | cut -c7-14)" = "ff 81 42" ] || fail "sprite_load : motif en \$0380"
[ "$(val _joy_idle)" = 00 ] || fail "joy2_read sans manette : $(val _joy_idle)"
[ "$(val _rnd_period_ok)" = 01 ] || fail "rnd8 : période différente de 255"
r=$(val _rnd_values 4); [ "$r" != "00 00 00 00" ] || fail "rnd8 : valeurs nulles"
[ "$(val _frames_waited 2)" = "05 00" ] || fail "wait_frame : compteur"
[ "$($D mem '$d020' 2 --bank io | cut -c7-11)" = "f6 f0" ] || fail "screen_colors : bordure/fond"
[ "$(( 0x$($D mem '$d800' 1 --bank io | cut -c7-8) & 15 ))" = 5 ] || fail "screen_clear : couleur"
$D screen --lower | head -1 | grep -q '^00|libc64 OK? *|$' || fail "screen_print : $($D screen --lower | head -1)"
[ "$($D mem '$d400' 5 --bank io | cut -c7-20)" = "45 1d 00 00 10" ] || fail "sid_beep/sid_release : voix 1"
[ "$($D mem '$d418' 1 --bank io | cut -c7-8)" = 0f ] || fail "sid_init : volume"
# irq / raster (lignes exactes : le handler lit $D012 au début de sa ligne).
[ "$(val _cia_slot)" = "$(val _cia_slot_again)" ] || fail "irq_register : réenregistrement depuis le handler -> autre emplacement"
[ "$((16#$(val _cia_count)))" -gt 10 ] || fail "handler CIA : $(val _cia_count) appels"
[ "$(val _irq_full)" = ff ] || fail "irq_register sur table pleine : $(val _irq_full)"
[ "$(val _raster_full)" = ff ] || fail "raster_register sur table pleine : $(val _raster_full)"
[ "$(val _line_a)$(val _line_b)" = 6467 ] || fail "raster : handlers de 100/103 appelés aux lignes $((16#$(val _line_a)))/$((16#$(val _line_b)))"
[ "$(val _mover_lines 2)" = "78 82" ] || fail "raster : handler déplacé 120<->130 appelé à $(val _mover_lines 2)"
[ "$(val _count_a)" = "$(val _count_a_frozen)" ] || fail "raster_unregister : le handler est encore appelé"
[ "$((16#$(val _b_delta)))" -ge 9 ] || fail "raster : le handler de 103 doit continuer après le retrait de celui de 100 ($((16#$(val _b_delta))) appels en 10 images)"
echo "ok : irq et raster (réenregistrement, tables pleines, retrait, lignes exactes)"
wt_expected=$(python3 - <<'PY'
import sys
sys.path.insert(0, "tools")
import mkworld
w, h, values, rows = mkworld.read_world("libc64/world/world.txt")
print(" ".join("%02x" % values[rows[y][x]][0] for x, y in ((0, 0), (w - 1, h - 1), (200, 75))) + " 00")
PY
)
[ "$(val _world_tiles 4)" = "$wt_expected" ] || fail "world_tile : $(val _world_tiles 4) au lieu de $wt_expected"
echo "ok : world_tile ($wt_expected : coins, intérieur, hors du monde)"
echo "ok : $(ls libc64/*/*.[cs] | wc -l) fonctions/modules vérifiés en exécution (rnd8 : $r ...)"
tools/stop.sh --quiet

# Le jeu : texte, sprite, x sur 9 bits.
tools/run.sh --headless --warp --monitor build/demo.prg >/dev/null || fail "run.sh demo"
sleep 0.5
$D screen --lower | sed -n 2p | grep -q 'MyGame - demo' || fail "demo : titre absent"
[ "$($D mem '$d015' 1 --bank io | cut -c7-8)" = 01 ] || fail "demo : sprite 0 inactif"
$D poke _ship_x 0x2c 0x01 >/dev/null
sleep 0.3
[ "$($D mem '$d000' 1 --bank io | cut -c7-8)$($D mem '$d010' 1 --bank io | cut -c7-8)" = 2c01 ] || fail "demo : x=300 non appliqué"
echo "ok : demo (titre, sprite, x au-delà de 255)"
# Bande de 3 lignes : capture de l'écran (rang de capture = ligne raster - 15).
$D capture build/test_band.png >/dev/null || fail "capture"
band=$(python3 tests/png_band.py build/test_band.png)
case "$band" in *"n=3") ;; *) fail "demo : bande de 3 lignes attendue (relevé : $band)" ;; esac
echo "ok : demo, bande bleue de 3 lignes raster ($band)"
tools/stop.sh --quiet

# Tileset : données générées à jour, installation en banque VIC 3 (écran
# $C000, motifs en $C800), Color RAM par défaut, rendu (drapeau de tileset_demo).
python3 tools/mktileset.py --check libc64/tileset/tileset.txt libc64/tileset/tileset_data.s \
    libc64/include/tiles.h libc64/include/tiles.inc 2>/dev/null || fail "tileset : fichiers générés pas à jour (make)"
tools/run.sh --headless --warp --monitor build/tileset_demo.prg >/dev/null || fail "run.sh tileset_demo"
sleep 0.5
[ "$($D mem _install_result 1 | cut -c7-8)" = 00 ] || fail "tileset_install : $($D mem _install_result 1)"
[ "$(( 0x$($D mem '$d018' 1 --bank io | cut -c7-8) & 0xfe ))" = 2 ] || fail "tileset : \$D018 = $($D mem '$d018' 1 --bank io | cut -c7-8) (02 attendu : écran \$C000, motifs \$C800)"
[ "$(( 0x$($D mem '$dd00' 1 --bank io | cut -c7-8) & 3 ))" = 0 ] || fail "tileset : banque VIC 3 non sélectionnée (\$DD00)"
[ "$(( 0x$($D mem '$d016' 1 --bank io | cut -c7-8) & 0x10 ))" = 16 ] || fail "tileset : mode multicolore inactif"
regs=$($D mem '$d021' 3 --bank io | cut -c7-14)
set -- $regs
[ "$(( 0x$1 & 15 )) $(( 0x$2 & 15 )) $(( 0x$3 & 15 ))" = "13 11 1" ] || fail "tileset : \$D021-\$D023 = $regs (13 11 1 attendus)"
[ "$($D mem '$ca00' 8 | cut -c7-29)" = "cc cc 33 33 cc cc 33 33" ] || fail "tileset : motif HERBE en \$CA00"
[ "$($D mem '$cfd8' 8 | cut -c7-29)" = "fe fc e0 c0 c0 80 80 00" ] || fail "tileset : motif LOGO_GWEN_BD en \$CFD8"
[ "$($D mem '$cfe0' 8 | cut -c7-29)" = "00 00 00 00 00 00 00 00" ] || fail "tileset : code libre \$FC non vide"
[ "$($D mem '$c000' 2 | cut -c7-11)" = "40 41" ] || fail "tileset : écran \$C000 (catalogue) = $($D mem '$c000' 2)"
col=$($D mem '$d800' 2 --bank io | cut -c7-11); set -- $col
[ "$(( 0x$1 & 15 )) $(( 0x$2 & 15 ))" = "5 10" ] || fail "tileset : Color RAM par défaut HERBE/ROUTE_H = $col (5 et 8+2 attendus)"
$D capture build/test_tiles.png >/dev/null || fail "capture tileset_demo"
flag=$(python3 - <<'PY'
import sys
sys.path.insert(0, "tests")
from png_band import rows_of
rows = rows_of("build/test_tiles.png")
y = 36 + 9 * 8 + 4                     # ligne 9 de l'écran
print(" ".join(str(rows[y][32 + c * 8 + 4]) for c in (28, 29, 30)))
PY
)
[ "$flag" = "6 1 2" ] || fail "tileset : drapeau rendu en couleurs $flag (6 1 2 attendues)"
echo "ok : tileset (données à jour, banque VIC 3, motifs en \$C800, Color RAM, rendu du drapeau)"
tools/stop.sh --quiet

# Monde : données compressées à jour, world_tile (libc64_test, plus haut),
# promenade dans mygame/monde (vues comparées au monde, blocage aux bords),
# panneau du bas de l'écran.
python3 tools/mkworld.py --check libc64/world/world.txt libc64/tileset/tileset.txt libc64/world/world_data.s \
    libc64/include/world.h libc64/include/world_defs.inc 2>/dev/null || fail "monde : fichiers générés pas à jour (make)"
tools/run.sh --headless --warp --monitor build/monde.prg >/dev/null || fail "run.sh monde"
python3 tests/world_test.py || fail "monde"
# Coupure vue qui défile / panneau (libc64/panel) : bande noire, panneau fixe,
# vue continue jusqu'à sa dernière ligne, pour les 8 décalages verticaux.
python3 tests/panel_test.py || fail "panneau"
# Joystick 2 au clavier (tools/vice/joystick.ini, chargé par run.sh) :
# ressources de VICE relues par le moniteur (commande « resource get »).
joy=$(python3 - <<'PY'
import sys
sys.path.insert(0, "tools")
import dbg
m = dbg.Monitor(6502, 5)
try:
    out = []
    for name in ("JoyDevice2", "KeySetEnable", "KeySet1North", "KeySet1South", "KeySet1West", "KeySet1East", "KeySet1Fire"):
        b = m.call(0x51, bytes([len(name)]) + name.encode()).body
        out.append(str(int.from_bytes(b[2:2 + b[1]], "little")))
    print(" ".join(out))
finally:
    m.exit_monitor()
    m.close()
PY
)
[ "$joy" = "2 1 65362 65364 65361 65363 32" ] || fail "joystick 2 au clavier : ressources VICE $joy"
echo "ok : joystick 2 au clavier (flèches + espace) configuré dans VICE"
tools/stop.sh --quiet

# demo2 : début de bande retardé par des NOP jusqu'au bord de l'écran : bord
# haut rectiligne sur toute la largeur, à chaque image (gigue de quelques
# cycles) ; bord bas non retardé (marche attendue au moins une fois).
tools/run.sh --headless --monitor build/demo2.prg >/dev/null || fail "run.sh demo2"
sleep 0.5
steps=0
for k in $(seq 1 10); do
    $D capture build/test_band.png >/dev/null || fail "capture demo2"
    band=$(python3 tests/png_band.py build/test_band.png)
    case "$band" in "haut=126 "*) ;; *) fail "demo2 : bord haut de la bande non rectiligne (image $k : $band)" ;; esac
    case "$band" in *"bas=128 "*) ;; *) steps=$((steps + 1)) ;; esac
    sleep 0.07
done
[ "$steps" -gt 0 ] || fail "demo2 : le bord bas devrait garder sa marche (fin de bande non retardée)"
echo "ok : demo2, bord haut rectiligne sur 10 images, bord bas avec marche ($steps/10)"
echo "libc64 OK"
