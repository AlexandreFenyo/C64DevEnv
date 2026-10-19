#!/usr/bin/env bash
# vscode-install.sh - construit l'extension VS Code du dépôt (tools/vscode/)
# en .vsix et l'installe dans le serveur VS Code de WSL (là où s'exécutent
# les extensions quand VS Code ouvre un dossier WSL).
#
# Usage : vscode-install.sh [--package-only]
#
#   --package-only   construit build/vscode/c64-vice-<version>.vsix sans l'installer
#
# L'extension ne contient que le lanceur : l'adaptateur de débogage est
# tools/dap.py du dossier ouvert, une modification de dap.py ne demande donc
# pas de réinstallation (seulement de relancer la session de débogage).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT="$ROOT/tools/vscode"
OUT="$ROOT/build/vscode"
PACKAGE_ONLY=0

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
    case "$1" in
        --package-only) PACKAGE_ONLY=1 ;;
        -h|--help) usage 0 ;;
        *) echo "vscode-install.sh: option inconnue : $1 (voir --help)" >&2; exit 1 ;;
    esac
    shift
done

mkdir -p "$OUT"
ID="$(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print("%s.%s" % (p["publisher"], p["name"]))' "$EXT/package.json")"
VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$EXT/package.json")"
VSIX="$OUT/c64-vice-$VERSION.vsix"

# Un .vsix est un zip : manifeste VSIX + [Content_Types].xml + extension/...
python3 - "$EXT" "$VSIX" <<'PY'
import json, os, sys, zipfile
ext, vsix = sys.argv[1], sys.argv[2]
p = json.load(open(os.path.join(ext, "package.json"), encoding="utf-8"))
manifest = """<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}" />
    <DisplayName>{display}</DisplayName>
    <Description xml:space="preserve">{description}</Description>
    <Categories>Debuggers,Programming Languages</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{engine}" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
      <Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value="" />
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
  </Assets>
</PackageManifest>
""".format(name=p["name"], version=p["version"], publisher=p["publisher"],
           display=p["displayName"], description=p["description"], engine=p["engines"]["vscode"])
types = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json" />
  <Default Extension=".js" ContentType="application/javascript" />
  <Default Extension=".md" ContentType="text/markdown" />
  <Default Extension=".vsixmanifest" ContentType="text/xml" />
</Types>
"""
with zipfile.ZipFile(vsix, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("extension.vsixmanifest", manifest)
    z.writestr("[Content_Types].xml", types)
    for d, _, files in os.walk(ext):
        for f in sorted(files):
            full = os.path.join(d, f)
            z.write(full, "extension/" + os.path.relpath(full, ext))
print("vscode-install.sh: %s" % vsix)
PY

[ "$PACKAGE_ONLY" = 1 ] && exit 0

# CLI : celle du terminal intégré de VS Code (remote-cli) si on y est, sinon
# celle du serveur VS Code installé dans WSL (~/.vscode-server).
CLI=()
if [ -n "${VSCODE_IPC_HOOK_CLI:-}" ] && command -v code >/dev/null 2>&1; then
    CLI=(code)
else
    server="$(ls -1t "$HOME"/.vscode-server/bin/*/bin/code-server 2>/dev/null | head -1 || true)"
    [ -n "$server" ] && CLI=("$server")
fi
if [ ${#CLI[@]} -eq 0 ]; then
    echo "vscode-install.sh: serveur VS Code introuvable dans WSL (~/.vscode-server)." >&2
    echo "  Ouvrez une première fois ce dossier depuis VS Code (extension WSL : code . dans Ubuntu)," >&2
    echo "  puis relancez make vscode." >&2
    exit 1
fi
"${CLI[@]}" --install-extension "$VSIX" --force
if "${CLI[@]}" --list-extensions --show-versions 2>/dev/null | grep -qi "^$ID@$VERSION$"; then
    echo "vscode-install.sh: extension $ID $VERSION installée (WSL). Dans VS Code : Developer: Reload Window."
else
    echo "vscode-install.sh: l'extension $ID n'apparaît pas dans la liste du serveur VS Code" >&2
    exit 1
fi
