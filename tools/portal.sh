#!/usr/bin/env bash
# portal.sh - gère le portail de développement (tools/portal.py).
#
# Usage : portal.sh start|stop|restart|status|logs|install|uninstall|check
#   start      démarre le portail en arrière-plan (ou le service s'il est installé)
#   stop       l'arrête
#   restart    stop + start (à faire après une modification de tools/portal.py)
#   status     état, URL, PID
#   logs       dernières lignes de var/portal.log
#   install    installe le service systemd utilisateur c64-portal : le portail
#              démarre tout seul à chaque ouverture de la distribution WSL
#   uninstall  arrête et supprime ce service
#   check      vérifie la cohérence outils/portail (portal.py --check)
#
# Variables : PORTAL_PORT (défaut 8064), PORTAL_HOST (défaut 127.0.0.1).
# Fichiers : var/portal.pid, var/portal.log (hors build/, que make clean efface).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAR="$ROOT/var"
PIDFILE="$VAR/portal.pid"
LOGFILE="$VAR/portal.log"
PORT="${PORTAL_PORT:-8064}"
HOST="${PORTAL_HOST:-127.0.0.1}"
UNIT="c64-portal.service"
UNIT_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$UNIT"
URL="http://localhost:$PORT"

die() { echo "portal.sh: $*" >&2; exit 1; }
mkdir -p "$VAR"

service_installed() { [ -f "$UNIT_FILE" ]; }

pid_alive() {
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

responding() {
    curl -fsS --max-time 2 "$URL/api/ping" >/dev/null 2>&1
}

wait_up() {
    for _ in $(seq 1 50); do
        responding && return 0
        sleep 0.2
    done
    return 1
}

do_start() {
    if service_installed; then
        systemctl --user start "$UNIT"
    else
        if pid_alive; then
            echo "portal.sh: déjà démarré (PID $(cat "$PIDFILE")) : $URL"
            return 0
        fi
        if responding; then
            die "le port $PORT répond déjà (autre instance ?) : $URL"
        fi
        echo "--- $(date '+%F %T') démarrage" >>"$LOGFILE"
        setsid python3 "$ROOT/tools/portal.py" --host "$HOST" --port "$PORT" \
            </dev/null >>"$LOGFILE" 2>&1 &
        echo "$!" >"$PIDFILE"
    fi
    wait_up || { tail -5 "$LOGFILE" >&2; die "le portail ne répond pas (voir $LOGFILE)"; }
    echo "portal.sh: portail démarré : $URL"
    grep -A20 "ATTENTION" "$LOGFILE" | tail -n +1 | grep -q "écart" 2>/dev/null \
        && echo "portal.sh: des écarts outils/portail sont signalés (portal.sh check)" || true
}

do_stop() {
    if service_installed; then
        systemctl --user stop "$UNIT" || true
    fi
    if pid_alive; then
        local pid
        pid="$(cat "$PIDFILE")"
        kill -TERM "$pid" 2>/dev/null || true
        for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
        kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
    echo "portal.sh: portail arrêté"
}

do_status() {
    local how="processus manuel"
    service_installed && how="service systemd $UNIT ($(systemctl --user is-active "$UNIT" 2>/dev/null || true))"
    if responding; then
        echo "portal.sh: en service sur $URL ($how)"
        pid_alive && echo "portal.sh: PID $(cat "$PIDFILE")"
        return 0
    fi
    echo "portal.sh: arrêté ($how)"
    return 3
}

do_install() {
    command -v systemctl >/dev/null || die "systemctl absent"
    systemctl --user show-environment >/dev/null 2>&1 \
        || die "systemd utilisateur indisponible : ajoutez [boot] systemd=true dans /etc/wsl.conf puis wsl --shutdown"
    # Une instance manuelle occuperait le port : on l'arrête d'abord.
    if pid_alive; then
        kill -TERM "$(cat "$PIDFILE")" 2>/dev/null || true
        sleep 0.5
        rm -f "$PIDFILE"
    fi
    mkdir -p "$(dirname "$UNIT_FILE")"
    # DISPLAY et PULSE_SERVER : environnement WSLg, pour que « Lancer » en
    # mode visible ouvre bien la fenêtre (et le son) même sans terminal.
    cat >"$UNIT_FILE" <<EOF
[Unit]
Description=Portail de développement C64 ($ROOT)
After=default.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=/usr/bin/python3 $ROOT/tools/portal.py --host $HOST --port $PORT
Environment=DISPLAY=${DISPLAY:-:0}
Environment=PULSE_SERVER=${PULSE_SERVER:-unix:/mnt/wslg/PulseServer}
Environment=PATH=/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
StandardOutput=append:$LOGFILE
StandardError=append:$LOGFILE
Restart=on-failure
RestartSec=2
# VICE lancé depuis le portail doit survivre à un redémarrage du portail.
KillMode=process

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable "$UNIT" >/dev/null 2>&1
    systemctl --user restart "$UNIT"
    wait_up || { journalctl --user -u "$UNIT" -n 20 --no-pager >&2 || true; die "le service ne répond pas"; }
    echo "portal.sh: service $UNIT installé et démarré : $URL"
    echo "portal.sh: il démarrera automatiquement à chaque ouverture de la distribution WSL"
}

do_uninstall() {
    if service_installed; then
        systemctl --user disable --now "$UNIT" >/dev/null 2>&1 || true
        rm -f "$UNIT_FILE"
        systemctl --user daemon-reload
        echo "portal.sh: service $UNIT supprimé"
    else
        echo "portal.sh: service $UNIT non installé"
    fi
}

case "${1:-}" in
    start) do_start ;;
    stop) do_stop ;;
    restart) do_stop; do_start ;;
    status) do_status ;;
    logs) tail -n "${2:-50}" "$LOGFILE" 2>/dev/null || echo "(pas de journal)" ;;
    install) do_install ;;
    uninstall) do_uninstall ;;
    check) python3 "$ROOT/tools/portal.py" --check ;;
    -h|--help|"") awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
                  [ -n "${1:-}" ] || exit 1 ;;
    *) die "commande inconnue : $1 (voir --help)" ;;
esac
