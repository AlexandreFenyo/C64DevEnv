#!/usr/bin/env bash
# vscode-open.sh - ouvre le dépôt dans VS Code (Windows, connecté à WSL), dans
# le profil C64, après avoir vérifié que l'extension du dépôt y est inscrite.
#
# Usage : vscode-open.sh [--profile NOM]
#
#   --profile NOM   profil VS Code (défaut : C64 ; créé vide s'il n'existe pas)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE=C64
usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
    case "$1" in
        --profile) [ $# -ge 2 ] || { echo "vscode-open.sh: --profile attend un nom" >&2; exit 1; }; PROFILE="$2"; shift ;;
        -h|--help) usage 0 ;;
        *) echo "vscode-open.sh: option inconnue : $1 (voir --help)" >&2; exit 1 ;;
    esac
    shift
done
command -v code >/dev/null || { echo "vscode-open.sh: commande code introuvable (VS Code pour Windows installé ?)" >&2; exit 1; }

# Extension du dépôt présente dans le profil ? Sinon : make vscode.
ID="$(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print("%s.%s" % (p["publisher"], p["name"]))' "$ROOT/tools/vscode/package.json")"
if ! grep -qs "\"$ID\"" "$HOME"/.vscode-server/data/User/profiles/*/extensions.json; then
    "$ROOT/tools/vscode-install.sh" --profile "$PROFILE"
fi
exec code --profile "$PROFILE" "$ROOT"
