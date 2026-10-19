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
echo "Monitor OK"
