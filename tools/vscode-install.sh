#!/usr/bin/env bash
# vscode-install.sh - construit l'extension VS Code du dépôt (tools/vscode/)
# en .vsix et l'installe dans le serveur VS Code de WSL (là où s'exécutent
# les extensions quand VS Code ouvre un dossier WSL).
#
# Usage : vscode-install.sh [--package-only] [--profile NOM]
#
#   --package-only   construit build/vscode/c64-vice-<version>.vsix sans l'installer
#   --profile NOM    profil VS Code où l'ajouter en plus du profil par défaut
#                    (défaut : C64 s'il existe ; "" pour aucun)
#
# Le serveur VS Code de WSL n'a pas d'option --profile : l'extension est
# installée (profil par défaut) puis inscrite dans la liste d'extensions du
# profil, ~/.vscode-server/data/User/profiles/<id>/extensions.json, dont
# l'identifiant est lu dans le stockage de VS Code côté Windows.
#
# L'extension ne contient que le lanceur : l'adaptateur de débogage est
# tools/dap.py du dossier ouvert, une modification de dap.py ne demande donc
# pas de réinstallation (seulement de relancer la session de débogage).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT="$ROOT/tools/vscode"
OUT="$ROOT/build/vscode"
PACKAGE_ONLY=0
PROFILE=C64

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
    case "$1" in
        --package-only) PACKAGE_ONLY=1 ;;
        --profile) [ $# -ge 2 ] || { echo "vscode-install.sh: --profile attend un nom" >&2; exit 1; }; PROFILE="$2"; shift ;;
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

# CLI du serveur VS Code installé dans WSL (~/.vscode-server) : installe dans
# le profil par défaut, quel que soit le profil de la fenêtre ouverte.
CLI=()
server="$(ls -1t "$HOME"/.vscode-server/bin/*/bin/code-server 2>/dev/null | head -1 || true)"
[ -n "$server" ] && CLI=("$server")
if [ ${#CLI[@]} -eq 0 ]; then
    echo "vscode-install.sh: serveur VS Code introuvable dans WSL (~/.vscode-server)." >&2
    echo "  Ouvrez une première fois ce dossier depuis VS Code (extension WSL : code . dans Ubuntu)," >&2
    echo "  puis relancez make vscode." >&2
    exit 1
fi
"${CLI[@]}" --install-extension "$VSIX" --force
if ! "${CLI[@]}" --list-extensions --show-versions 2>/dev/null | grep -qi "^$ID@$VERSION$"; then
    echo "vscode-install.sh: l'extension $ID n'apparaît pas dans la liste du serveur VS Code" >&2
    exit 1
fi
echo "vscode-install.sh: extension $ID $VERSION installée (WSL, profil par défaut)."

# Inscription dans le profil nommé.
if [ -n "$PROFILE" ]; then
    python3 - "$ID" "$PROFILE" <<'PY'
import glob, json, os, sys
ext_id, profile = sys.argv[1], sys.argv[2]
home = os.path.expanduser("~")
# Profils déclarés côté Windows (%APPDATA%\Code\User\globalStorage\storage.json).
pid = None
for storage in glob.glob("/mnt/c/Users/*/AppData/Roaming/Code/User/globalStorage/storage.json"):
    try:
        with open(storage, encoding="utf-8") as f:
            for p in json.load(f).get("userDataProfiles", []):
                if p.get("name") == profile:
                    pid = p.get("location")
    except (OSError, ValueError):
        continue
if not pid:
    print("vscode-install.sh: profil VS Code « %s » introuvable : extension seulement dans le profil "
          "par défaut (créez-le avec : code --profile %s ~/C64DevEnv, puis relancez make vscode)" % (profile, profile))
    sys.exit(0)
with open(os.path.join(home, ".vscode-server/extensions/extensions.json"), encoding="utf-8") as f:
    entry = next((e for e in json.load(f) if e["identifier"]["id"].lower() == ext_id.lower()), None)
if entry is None:
    sys.exit("vscode-install.sh: %s absente de ~/.vscode-server/extensions/extensions.json" % ext_id)
path = os.path.join(home, ".vscode-server/data/User/profiles", pid, "extensions.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
except (OSError, ValueError):
    entries = []
entries = [e for e in entries if e["identifier"]["id"].lower() != ext_id.lower()] + [entry]
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(entries, f)
os.replace(tmp, path)
print("vscode-install.sh: extension inscrite dans le profil « %s » (%s)." % (profile, pid))
PY
fi
echo "vscode-install.sh: dans VS Code : Developer: Reload Window."
