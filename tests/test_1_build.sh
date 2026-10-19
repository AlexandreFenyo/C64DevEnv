#!/usr/bin/env bash
# Test 1 : build complet depuis zéro, sans warning ni erreur de cc65.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

make clean >/dev/null 2>&1
if ! make >"$LOG" 2>&1; then
    cat "$LOG"
    echo "ECHEC : make a échoué"
    exit 1
fi
if grep -iE '(^|: )(warning|error)' "$LOG"; then
    echo "ECHEC : warnings/erreurs dans la sortie de make"
    exit 1
fi

ok=0
for p in $(make -s list); do
    prg="build/$p.prg"
    lbl="build/$p.labels"
    [ -s "$prg" ] || { echo "ECHEC : $prg absent ou vide"; exit 1; }
    [ -s "$lbl" ] || { echo "ECHEC : $lbl absent ou vide"; exit 1; }
    # Un .prg C64 commence par l'adresse de chargement $0801.
    head="$(head -c 2 "$prg" | od -An -tx1 | tr -d ' \n')"
    [ "$head" = "0108" ] || { echo "ECHEC : $prg ne commence pas par \$0801 (lu : $head)"; exit 1; }
    echo "ok : $prg ($(stat -c %s "$prg") octets), $(wc -l <"$lbl") labels"
    ok=$((ok + 1))
done
[ "$ok" -ge 2 ] || { echo "ECHEC : au moins hello et hello_c attendus"; exit 1; }
grep -q '\.loop$' build/hello.labels || { echo "ECHEC : label 'loop' absent de build/hello.labels"; exit 1; }
grep -q '\._main$' build/hello_c.labels || { echo "ECHEC : label '_main' absent de build/hello_c.labels"; exit 1; }
echo "Build OK sans warning ($ok programmes)"
