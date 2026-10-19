#!/usr/bin/env bash
# install.sh - installe et vérifie la chaîne de développement C64 (cc65 + VICE)
# sous Ubuntu/WSL2. Idempotent : relançable sans effet de bord.
#
# Usage : tools/install.sh [--build-vice] [--no-apt]
#   --build-vice : force la compilation de VICE depuis les sources
#   --no-apt     : ne tente jamais d'appeler apt (vérification seule)
#
# Codes de sortie : 0 si tout est opérationnel, 1 sinon.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VICE_MIN_VERSION="3.5"
VICE_SRC_VERSION="${VICE_SRC_VERSION:-3.10}"
VICE_TARBALL_URL="https://sourceforge.net/projects/vice-emu/files/releases/vice-${VICE_SRC_VERSION}.tar.gz/download"
APT_PACKAGES=(build-essential cc65 vice python3 python3-pip xvfb netcat-openbsd imagemagick git make curl)
# Paquets nécessaires uniquement pour compiler VICE depuis les sources.
VICE_BUILD_PACKAGES=(autoconf automake libtool pkg-config libgtk-3-dev libglew-dev
    libpulse-dev libasound2-dev libpng-dev libgif-dev flex bison xa65 dos2unix texinfo)
USER_ROM_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/vice/C64"

FORCE_BUILD=0
NO_APT=0
for arg in "$@"; do
    case "$arg" in
        --build-vice) FORCE_BUILD=1 ;;
        --no-apt) NO_APT=1 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "install.sh: option inconnue : $arg" >&2; exit 1 ;;
    esac
done

info() { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[  OK   ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[ WARN  ]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[ FAIL  ]\033[0m %s\n' "$*" >&2; }
die()  { fail "$*"; exit 1; }

# ---------------------------------------------------------------------------
# 1. Paquets apt
# ---------------------------------------------------------------------------
missing_packages() {
    local p
    for p in "$@"; do
        dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || echo "$p"
    done
}

apt_install() {
    local -a missing
    mapfile -t missing < <(missing_packages "$@")
    if [ ${#missing[@]} -eq 0 ]; then
        ok "paquets déjà installés : $*"
        return 0
    fi
    if [ "$NO_APT" = 1 ]; then
        die "paquets manquants (--no-apt actif) : ${missing[*]}"
    fi
    info "installation apt de : ${missing[*]} (sudo requis)"
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
    mapfile -t missing < <(missing_packages "$@")
    [ ${#missing[@]} -eq 0 ] || die "paquets toujours manquants après apt : ${missing[*]}"
    ok "paquets installés"
}

apt_install "${APT_PACKAGES[@]}"

command -v cl65 >/dev/null || die "cl65 introuvable après installation de cc65"
command -v python3 >/dev/null || die "python3 introuvable"

# ---------------------------------------------------------------------------
# 2. VICE : ROMs C64 et support du moniteur binaire
# ---------------------------------------------------------------------------
vice_version() {
    # x64sc --version affiche "x64sc (VICE 3.7.1)" ; sans DISPLAY il peut
    # se plaindre mais imprime quand même la version.
    "$1" --version 2>/dev/null | grep -oE 'VICE [0-9]+(\.[0-9]+)*' | head -1 | cut -d' ' -f2
}

version_ge() { # version_ge A B : vrai si A >= B
    [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]
}

rom_present() {
    # Un jeu de ROMs C64 est utilisable si kernal, basic et chargen existent
    # dans l'un des répertoires que VICE consulte.
    local d
    for d in "$USER_ROM_DIR" /usr/local/share/vice/C64 /usr/local/lib/vice/C64 \
             /usr/share/vice/C64 /usr/lib/vice/C64 /usr/lib/x86_64-linux-gnu/vice/C64; do
        if ls "$d"/kernal* >/dev/null 2>&1 && ls "$d"/basic* >/dev/null 2>&1 \
           && ls "$d"/chargen* >/dev/null 2>&1; then
            echo "$d"
            return 0
        fi
    done
    return 1
}

vice_supports_binarymonitor() {
    # -help exige un affichage ; xvfb-run fournit un X virtuel.
    xvfb-run -a "$1" -help 2>/dev/null | grep -qE '^\s*-binarymonitor\b'
}

download_vice_source() {
    local dest="$1"
    mkdir -p "$dest"
    local tarball="$dest/vice-${VICE_SRC_VERSION}.tar.gz"
    if [ ! -s "$tarball" ]; then
        info "téléchargement de VICE ${VICE_SRC_VERSION}"
        curl -fL --retry 3 -o "$tarball" "$VICE_TARBALL_URL" \
            || die "téléchargement impossible : $VICE_TARBALL_URL"
    fi
    if [ ! -d "$dest/vice-${VICE_SRC_VERSION}" ]; then
        tar -xzf "$tarball" -C "$dest" || die "archive VICE corrompue : $tarball"
    fi
    echo "$dest/vice-${VICE_SRC_VERSION}"
}

install_roms_from_source() {
    # Le paquet Ubuntu (dfsg) retire les ROMs ; elles sont dans les sources
    # officielles. VICE >= 3.5 lit ~/.local/share/vice/<machine>/ avant les
    # répertoires système : aucun droit root nécessaire.
    local srcdir
    srcdir="$(download_vice_source "$ROOT/build/vice-src")"
    local romsrc="$srcdir/data/C64"
    [ -d "$romsrc" ] || die "répertoire de ROMs absent des sources : $romsrc"
    mkdir -p "$USER_ROM_DIR"
    cp -n "$romsrc"/* "$USER_ROM_DIR"/ 2>/dev/null || true
    # Les lecteurs 1541 sont utiles pour les images disque.
    if [ -d "$srcdir/data/DRIVES" ]; then
        mkdir -p "$(dirname "$USER_ROM_DIR")/DRIVES"
        cp -n "$srcdir/data/DRIVES"/* "$(dirname "$USER_ROM_DIR")/DRIVES"/ 2>/dev/null || true
    fi
    ok "ROMs C64 copiées dans $USER_ROM_DIR"
}

build_vice_from_source() {
    info "compilation de VICE ${VICE_SRC_VERSION} depuis les sources (GTK3, ROMs incluses)"
    apt_install "${VICE_BUILD_PACKAGES[@]}"
    local srcdir
    srcdir="$(download_vice_source "$ROOT/build/vice-src")"
    (
        cd "$srcdir"
        [ -x configure ] || ./autogen.sh
        ./configure --prefix=/usr/local --enable-gtk3ui --disable-pdf-docs \
            --with-pulse --with-alsa --with-png --disable-html-docs >configure.log 2>&1 \
            || { tail -30 configure.log; die "configure VICE a échoué (voir $srcdir/configure.log)"; }
        make -j"$(nproc)" >make.log 2>&1 \
            || { tail -30 make.log; die "make VICE a échoué (voir $srcdir/make.log)"; }
        sudo make install >install.log 2>&1 \
            || { tail -30 install.log; die "make install VICE a échoué"; }
    )
    hash -r
    ok "VICE installé dans /usr/local (x64sc = $(command -v x64sc))"
}

X64SC="$(command -v x64sc || true)"
[ -n "$X64SC" ] || die "x64sc introuvable"
VICE_VER="$(vice_version "$X64SC")"

NEED_BUILD=0
if [ "$FORCE_BUILD" = 1 ]; then
    NEED_BUILD=1
elif ! version_ge "$VICE_VER" "$VICE_MIN_VERSION"; then
    warn "VICE $VICE_VER < $VICE_MIN_VERSION : moniteur binaire absent"
    NEED_BUILD=1
elif ! vice_supports_binarymonitor "$X64SC"; then
    warn "x64sc n'accepte pas -binarymonitor"
    NEED_BUILD=1
fi

if [ "$NEED_BUILD" = 1 ]; then
    if [ "$NO_APT" = 1 ]; then die "VICE doit être compilé mais --no-apt est actif"; fi
    build_vice_from_source
    X64SC="$(command -v x64sc)"
    VICE_VER="$(vice_version "$X64SC")"
    vice_supports_binarymonitor "$X64SC" || die "VICE compilé sans -binarymonitor ?!"
fi
ok "VICE $VICE_VER avec -binarymonitor ($X64SC)"

if ROM_DIR="$(rom_present)"; then
    ok "ROMs C64 présentes dans $ROM_DIR"
else
    warn "ROMs C64 absentes (paquet Ubuntu dfsg) : récupération depuis les sources VICE"
    install_roms_from_source
    ROM_DIR="$(rom_present)" || die "ROMs toujours absentes après installation"
fi

# Test réel : boot headless du C64 jusqu'au READY, screenshot non noir.
info "test de boot headless de x64sc"
mkdir -p "$ROOT/build"
BOOT_PNG="$ROOT/build/install-boot.png"
rm -f "$BOOT_PNG"
set +e
timeout 60 env -u WAYLAND_DISPLAY GDK_BACKEND=x11 xvfb-run -a "$X64SC" -default -sounddev dummy \
    -warp -limitcycles 4000000 -exitscreenshot "$BOOT_PNG" >"$ROOT/build/install-boot.log" 2>&1
set -e
if [ -s "$BOOT_PNG" ] && [ "$(convert "$BOOT_PNG" -format '%[fx:standard_deviation>0.01]' info:)" = "1" ]; then
    ok "boot C64 headless validé ($BOOT_PNG)"
    BOOT_STATE="OK"
else
    fail "boot headless échoué, voir $ROOT/build/install-boot.log"
    grep -iE 'rom|error' "$ROOT/build/install-boot.log" | head -5 || true
    BOOT_STATE="ECHEC"
fi

# ---------------------------------------------------------------------------
# 3. WSLg : affichage graphique
# ---------------------------------------------------------------------------
WSLG_STATE="ECHEC"
if [ -z "${DISPLAY:-}" ]; then
    fail "DISPLAY n'est pas défini : WSLg inactif ?"
    cat <<'EOF'
  Diagnostic :
   - Vérifiez que Windows 11 et WSL sont à jour : "wsl --update" puis "wsl --shutdown" depuis PowerShell.
   - WSLg exige systemd/WSL2 : "wsl -l -v" doit indiquer VERSION 2.
   - /mnt/wslg doit exister ; DISPLAY vaut normalement ":0".
   - Dans ~/.bashrc ou ~/.zshrc, ne pas écraser DISPLAY.
EOF
elif [ ! -d /mnt/wslg ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    warn "DISPLAY=$DISPLAY mais /mnt/wslg absent : affichage non-WSLg (serveur X tiers ?)"
    WSLG_STATE="INCONNU (DISPLAY=$DISPLAY)"
fi
wslg_diagnostic() {
    cat <<EOF
  Diagnostic :
   - Le serveur X de WSLg (XWayland, DISPLAY=$DISPLAY) accepte la connexion
     mais ne répond pas : WSLg est probablement en boucle de redémarrage.
EOF
    if [ -r /mnt/wslg/weston.log ]; then
        local n
        n=$(grep -c "^\[.*\] weston [0-9]" /mnt/wslg/weston.log 2>/dev/null || echo 0)
        echo "   - /mnt/wslg/weston.log contient $n démarrages de weston ; les derniers :"
        grep "^\[.*\] weston [0-9]" /mnt/wslg/weston.log | tail -4 | cut -c1-15 | sed 's/^/       /'
        grep -q "unable to checkDescriptor" /mnt/wslg/weston.log \
            && echo "   - 'unable to checkDescriptor' : la liaison RDP avec Windows (msrdc.exe) se coupe."
    fi
    cat <<'EOF'
   - Remède (côté Windows, PowerShell) : "wsl --shutdown", puis relancer la
     distribution ; si cela persiste : "wsl --update" et redémarrer Windows.
   - Les commandes --headless (xvfb) restent utilisables sans WSLg.
EOF
}

if [ -n "${DISPLAY:-}" ]; then
    info "test du serveur X sur DISPLAY=$DISPLAY"
    # Sonde légère : xdpyinfo doit répondre en moins de 10 s. Sous WSLg,
    # XWayland est lancé à la demande, d'où une marge généreuse.
    if timeout 10 xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        info "test d'ouverture d'une fenêtre (se ferme seule)"
        # x64sc est lui-même la fenêtre de test : 1,5 M cycles en warp, sans
        # son, puis sortie automatique. Évite une dépendance à xterm/xmessage.
        set +e
        timeout 30 env -u WAYLAND_DISPLAY GDK_BACKEND=x11 "$X64SC" -default -sounddev dummy \
            -warp -limitcycles 1500000 >"$ROOT/build/install-wslg.log" 2>&1
        rc=$?
        set -e
        # VICE renvoie 1 avec "cycle limit reached" : c'est le chemin normal.
        if grep -q "cycle limit reached" "$ROOT/build/install-wslg.log"; then
            ok "fenêtre affichée puis fermée automatiquement (WSLg fonctionnel)"
            WSLG_STATE="OK (DISPLAY=$DISPLAY)"
        else
            fail "x64sc n'a pas pu ouvrir de fenêtre (rc=$rc), voir build/install-wslg.log"
            grep -iE 'display|gtk|error' "$ROOT/build/install-wslg.log" | head -5 || true
            WSLG_STATE="ECHEC (DISPLAY=$DISPLAY)"
        fi
    else
        fail "le serveur X ne répond pas sur DISPLAY=$DISPLAY"
        wslg_diagnostic
        WSLG_STATE="ECHEC (serveur X muet sur DISPLAY=$DISPLAY)"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Récapitulatif
# ---------------------------------------------------------------------------
echo
echo "================ Récapitulatif ================"
printf '%-14s %s\n' "cc65 :"    "$(cl65 --version 2>&1 | head -1)"
printf '%-14s %s\n' "VICE :"    "$VICE_VER ($X64SC)"
printf '%-14s %s\n' "python :"  "$(python3 --version)"
printf '%-14s %s\n' "ROMs C64 :" "$ROM_DIR"
printf '%-14s %s\n' "boot test :" "$BOOT_STATE"
printf '%-14s %s\n' "WSLg :"    "$WSLG_STATE"
echo "==============================================="

[ "$BOOT_STATE" = "OK" ] || exit 1
case "$WSLG_STATE" in OK*) exit 0 ;; *) exit 1 ;; esac
