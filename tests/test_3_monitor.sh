#!/usr/bin/env bash
# Test 3 : hello.prg en headless avec --monitor, puis via dbg.py :
#   - lecture de la valeur témoin ($02FF = $42),
#   - lecture de la mémoire écran (chaîne affichée),
#   - point d'arrêt sur le label 'loop', continue, vérification de l'arrêt,
#   - arrêt propre de VICE.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
DBG="tools/dbg.py"

cleanup() { tools/stop.sh --quiet --all; }
trap cleanup EXIT

fail() { echo "ECHEC : $*"; exit 1; }

[ -f build/hello.prg ] || make >/dev/null || fail "build"

# dbg.py doit expliquer clairement l'absence de VICE.
tools/stop.sh --quiet --all
out="$($DBG regs 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "dbg.py sans VICE : code $rc attendu 2 (sortie : $out)"
echo "$out" | grep -q "VICE n'est pas lancé" || fail "message 'VICE n'est pas lancé' absent : $out"
echo "ok : dbg.py sans VICE -> '$out'"

tools/run.sh --headless --warp --monitor build/hello.prg || fail "run.sh --monitor"

# run.sh ne rend la main qu'une fois l'autostart terminé (sinon une commande
# du moniteur peut le bloquer) : état "ready" et "AUTOSTART: Done" au journal.
[ "$(cat build/vice.state 2>/dev/null)" = "ready" ] || fail "build/vice.state != ready au retour de run.sh"
grep -q "AUTOSTART: Done" build/vice.log || fail "autostart non terminé au retour de run.sh"
echo "ok : autostart terminé avant de rendre la main"

# Attend que l'autostart ait lancé le programme : la valeur témoin apparaît.
witness=""
for _ in $(seq 1 100); do
    witness="$($DBG mem '$02FF' 1 2>/dev/null | awk 'NR==1 {print $2}')"
    [ "$witness" = "42" ] && break
    sleep 0.2
done
[ "$witness" = "42" ] || fail "valeur témoin \$02FF = '$witness', attendu 42"
echo "ok : témoin \$02FF = \$42"

# Mémoire écran : la chaîne affichée par le programme.
screen="$($DBG screen)" || fail "dbg.py screen"
echo "$screen" | head -2
echo "$screen" | grep -q "HELLO FROM CA65!" || fail "chaîne 'HELLO FROM CA65!' absente de l'écran"
echo "$screen" | grep -q "C64 DEV ENV READY." || fail "seconde ligne absente de l'écran"
echo "ok : écran"

# Registres : format stable.
regs="$($DBG regs)" || fail "dbg.py regs"
echo "$regs" | grep -qE '^A=[0-9a-f]{2} X=[0-9a-f]{2} Y=[0-9a-f]{2} SP=[0-9a-f]{2} PC=[0-9a-f]{4} FLAGS=' \
    || fail "format de regs inattendu : $regs"
echo "ok : $regs"

# Labels : résolution par nom.
loop_addr="$($DBG label loop | awk '$1=="loop" {print $3}')"
[ "$loop_addr" = '$0831' ] || fail "label loop = '$loop_addr', attendu \$0831"

# Point d'arrêt sur un label, continue, arrêt attendu.
bp="$($DBG break loop)" || fail "dbg.py break loop"
echo "$bp" | grep -q "checkpoint 1 \$0831 (loop)" || fail "réponse break inattendue : $bp"
cont="$($DBG cont)" || fail "dbg.py cont"
[ "$cont" = "resumed" ] || fail "cont : '$cont'"
stop="$($DBG wait 5)" || fail "pas d'arrêt sur le point d'arrêt : $stop"
echo "$stop" | grep -q "stopped PC=0831 (loop) checkpoint=1" || fail "arrêt inattendu : $stop"
echo "ok : $stop"
pc="$($DBG regs | sed -n 's/.*PC=\([0-9a-f]*\).*/\1/p')"
[ "$pc" = "0831" ] || fail "PC=$pc après arrêt, attendu 0831"
st="$($DBG status)"
echo "$st" | grep -q "^stopped" || fail "status : '$st'"

# Pas à pas : 'loop: jmp loop' reste en place, A inchangé.
step="$($DBG step)" || fail "dbg.py step"
echo "$step" | grep -q "PC=0831" || fail "step : $step"

# Suppression du point d'arrêt et reprise : l'émulateur tourne à nouveau.
$DBG delete 1 >/dev/null || fail "delete"
$DBG list | grep -q "no checkpoints" || fail "list après delete"
$DBG cont >/dev/null || fail "cont final"
sleep 0.3
st="$($DBG status)"
[ "$st" = "running" ] || fail "status après cont : '$st'"
echo "ok : point d'arrêt, step, delete, cont"

# Écriture mémoire et dump binaire.
$DBG poke '$02FE' 0x99 >/dev/null || fail "poke"
$DBG dump '$02FE' 2 build/test_dump.bin >/dev/null || fail "dump"
[ "$(od -An -tx1 build/test_dump.bin | tr -d ' \n')" = "9942" ] || fail "dump : contenu inattendu"
echo "ok : poke/dump"

# Infos source (build/vice.dbg), désassemblage, banques mémoire.
w="$($DBG where)" || fail "where"
echo "$w" | grep -q "^PC=0831 (loop) examples/hello/hello.s:38  jmp loop" || fail "where : '$w'"
d="$($DBG disasm)" || fail "disasm"
echo "$d" | grep -qE '^>   0831  4c 31 08  JMP loop$' || fail "disasm : instruction courante absente : $d"
echo "$d" | grep -qE '^          message:$' || fail "disasm : label message absent"
echo "$d" | grep -qE '\.byte \$48,\$45,\$4c' || fail "disasm : RODATA non affiché en .byte"
$DBG lines hello.s | grep -qx 'examples/hello/hello.s:18 $080d-$080f' || fail "lines : jsr CLRSCR en \$080d attendu"
$DBG segments | grep -qE '^CODE +\$080d-' || fail "segments : CODE en \$080d attendu"
$DBG banks | grep -qx 'bank 1 ram' || fail "banks : banque ram attendue"
[ "$($DBG mem '$a000' 2 --bank rom | cut -c7-11)" = "94 e3" ] || fail "mem --bank rom : vecteur BASIC \$e394 attendu en \$a000"
echo "ok : where, disasm, lines, segments, banks, --bank"

# Pas à pas depuis l'entrée : jump, next par-dessus un JSR (sans s'arrêter
# dans l'IRQ), step, where sur la bonne ligne source.
$DBG jump start | grep -qx 'stopped PC=080d (start)' || fail "jump start"
$DBG next | grep -q 'PC=0810' || fail "next par-dessus JSR CLRSCR : PC=0810 attendu"
$DBG step | grep -q 'PC=0812' || fail "step : PC=0812 attendu"
$DBG where | grep -q 'hello.s:20  sta VIC_BORDERCOLOR' || fail "where après step : ligne 20 attendue"
# next avec un point d'arrêt dans le sous-programme : arrêt dessus.
$DBG jump start >/dev/null
$DBG break '$e544' >/dev/null
$DBG next | grep -q 'PC=e544' || fail "next : arrêt sur le point d'arrêt dans le sous-programme attendu"
$DBG delete 1 >/dev/null
[ "$($DBG list)" = "no checkpoints" ] || fail "next ne doit laisser aucun point d'arrêt temporaire"
$DBG jump loop >/dev/null
$DBG cont >/dev/null
echo "ok : jump, next (JSR), step, point d'arrêt dans un sous-programme"

# Arrêt propre via le moniteur, puis plus aucun x64sc vivant.
$DBG quit >/dev/null || fail "quit"
for _ in $(seq 1 50); do
    pgrep -u "$(id -u)" -x x64sc >/dev/null 2>&1 || break
    ps -u "$(id -u)" -o stat=,comm= | grep -qE '^[^Z]\S* +x64sc$' || break
    sleep 0.1
done
if ps -u "$(id -u)" -o stat=,comm= | grep -qE '^[^Z]\S* +x64sc$'; then
    fail "x64sc encore vivant après quit"
fi
echo "ok : VICE arrêté proprement"

# Relance au clavier : hello_rts revient au BASIC ; point d'arrêt sur
# l'entrée, « run » tapé au clavier, arrêt attendu sur start.
tools/run.sh --headless --warp --monitor build/hello_rts.prg >/dev/null || fail "run.sh hello_rts"
$DBG break start >/dev/null || fail "break start (hello_rts)"
$DBG type 'run\n' | grep -qx 'typed 4 chars' || fail "type run"
$DBG wait 5 | grep -q '^stopped PC=080d (start)' || fail "RUN tapé : arrêt sur start attendu"
$DBG where | grep -q 'hello_rts.s:15  jsr CLRSCR' || fail "where (hello_rts)"
tools/stop.sh --quiet
echo "ok : type (RUN au clavier) puis arrêt sur le point d'entrée"
echo "Monitor OK"
