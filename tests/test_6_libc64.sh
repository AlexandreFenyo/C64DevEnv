#!/usr/bin/env bash
# Test 6 : bibliothèque libc64 et premier programme de mygame/.
#   - build/libc64.lib contient un module par fichier de libc64/ ;
#   - demo n'incorpore que les modules qu'il appelle (rnd8, sprite_hide absents) ;
#   - examples/libc64_test appelle toutes les fonctions : résultats vérifiés en mémoire ;
#   - demo tourne : texte, sprite, position x sur 9 bits.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
D=tools/dbg.py
fail() { echo "ECHEC : $*"; exit 1; }
trap 'tools/stop.sh --quiet' EXIT

make >/dev/null || fail "make"
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
echo "ok : 13 fonctions vérifiées en exécution (rnd8 : $r ...)"
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
echo "libc64 OK"
