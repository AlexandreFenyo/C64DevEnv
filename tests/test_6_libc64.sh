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
for c in IRQ_MAX_HANDLERS IRQ_SRC_CIA IRQ_SRC_VIC RASTER_MAX_HANDLERS RASTER_LEAD; do
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
[ "$((16#$(val _count_b)))" -gt "$((16#$(val _count_a)))" ] || fail "raster : le handler de 103 doit continuer après le retrait de celui de 100"
echo "ok : irq et raster (réenregistrement, tables pleines, retrait, lignes exactes)"
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
# Bande de 3 lignes : capture de l'écran, colonne x=100 (capture : ligne raster - 15).
$D capture build/test_band.png >/dev/null || fail "capture"
band=$(python3 - <<'PY'
import struct, zlib
d = open("build/test_band.png", "rb").read()
pos, idat, w = 8, b"", 0
while pos < len(d):
    n = struct.unpack(">I", d[pos:pos + 4])[0]
    t, body = d[pos + 4:pos + 8], d[pos + 8:pos + 8 + n]
    if t == b"IHDR":
        w = struct.unpack(">I", body[:4])[0]
    elif t == b"IDAT":
        idat += body
    pos += 12 + n
raw = zlib.decompress(idat)
rows = [y for y in range(len(raw) // (w + 1)) if raw[y * (w + 1) + 1 + 100] == 6]
print(len(rows), rows[0] + 15 if rows else -1)
PY
)
[ "$band" = "3 141" ] || fail "demo : bande attendue de 3 lignes à partir de la ligne 141 (relevé : $band)"
echo "ok : demo, bande bleue de 3 lignes raster (141-143, colonne x=100)"
echo "libc64 OK"
