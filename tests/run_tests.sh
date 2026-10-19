#!/usr/bin/env bash
# run_tests.sh - exécute tous les tests tests/test_*.sh dans l'ordre.
# Code de sortie non nul si l'un d'eux échoue. Nettoie les VICE restants.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

pass=0
fail=0
failed=()
for t in "$ROOT"/tests/test_*.sh; do
    name="$(basename "$t" .sh)"
    echo "=============================== $name"
    if bash "$t"; then
        echo "--- PASS $name"
        pass=$((pass + 1))
    else
        echo "--- FAIL $name"
        fail=$((fail + 1))
        failed+=("$name")
    fi
    # Aucun VICE orphelin entre deux tests.
    "$ROOT/tools/stop.sh" --quiet --all
done

echo "==============================="
echo "Tests : $pass réussi(s), $fail échoué(s)"
if [ "$fail" -gt 0 ]; then
    echo "Échecs : ${failed[*]}"
    exit 1
fi
if pgrep -u "$(id -u)" -x x64sc >/dev/null 2>&1 && ps -u "$(id -u)" -o stat=,comm= | grep -qE '^[^Z]\S* +x64sc$'; then
    echo "ERREUR : un x64sc orphelin subsiste"
    exit 1
fi
exit 0
