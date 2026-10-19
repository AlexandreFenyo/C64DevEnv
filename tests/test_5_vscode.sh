#!/usr/bin/env bash
# Test 5 : débogage VS Code. tools/dap.py est piloté comme par VS Code
# (protocole DAP sur stdin/stdout) : pas à pas asm et C, variables, points
# d'arrêt, attach ; l'extension (tools/vscode/) doit se construire en .vsix
# et déclarer les mêmes paramètres que ceux lus par dap.py.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
[ -f build/squares_c.prg ] || make >/dev/null || { echo "ECHEC : build"; exit 1; }
tools/vscode-install.sh --package-only || { echo "ECHEC : construction du .vsix"; exit 1; }
unzip -l build/vscode/c64-vice-*.vsix | grep -q 'extension/extension.js' || { echo "ECHEC : .vsix incomplet"; exit 1; }
exec python3 tests/dap_test.py
