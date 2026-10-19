#!/usr/bin/env bash
# stop.sh - arrête proprement l'instance VICE lancée par run.sh.
#
# Usage : stop.sh [--quiet] [--all]
#   --quiet  silencieux s'il n'y a rien à arrêter
#   --all    tue aussi tout x64sc/xvfb-run orphelin de cet utilisateur
#
# Lit build/vice.pid (groupe de processus créé par setsid dans run.sh),
# envoie SIGTERM au groupe, puis SIGKILL après 3 s si nécessaire.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/build/vice.pid"
QUIET=0
ALL=0
for arg in "$@"; do
    case "$arg" in
        --quiet) QUIET=1 ;;
        --all) ALL=1 ;;
        -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "stop.sh: option inconnue : $arg" >&2; exit 1 ;;
    esac
done

say() { [ "$QUIET" = 1 ] || echo "stop.sh: $*"; }

stop_group() {
    local pid="$1"
    kill -0 "$pid" 2>/dev/null || return 1
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    local i
    for i in $(seq 1 30); do
        kill -0 "$pid" 2>/dev/null || return 0
        sleep 0.1
    done
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
    sleep 0.2
    ! kill -0 "$pid" 2>/dev/null
}

rc=0
# Démon dbg.py (lancé par run.sh --monitor) : à arrêter avant VICE pour
# qu'il ne signale pas une déconnexion inopinée.
DBGPID="$ROOT/build/dbg.pid"
if [ -f "$DBGPID" ]; then
    DP="$(cat "$DBGPID")"
    if [[ "$DP" =~ ^[0-9]+$ ]] && kill -0 "$DP" 2>/dev/null; then
        kill -TERM "$DP" 2>/dev/null
        for _ in $(seq 1 20); do kill -0 "$DP" 2>/dev/null || break; sleep 0.1; done
        kill -KILL "$DP" 2>/dev/null
        say "démon dbg.py (PID $DP) arrêté"
    fi
    rm -f "$DBGPID"
fi
rm -f "${C64_DBG_SOCK:-$ROOT/build/dbg.sock}" "$ROOT/build/vice.state"

if [ -f "$PIDFILE" ]; then
    PID="$(cat "$PIDFILE")"
    if [[ "$PID" =~ ^[0-9]+$ ]] && stop_group "$PID"; then
        say "VICE (PID $PID) arrêté"
    elif [[ "$PID" =~ ^[0-9]+$ ]] && ! kill -0 "$PID" 2>/dev/null; then
        say "VICE (PID $PID) n'était plus en cours d'exécution"
    else
        echo "stop.sh: impossible d'arrêter le PID $PID" >&2
        rc=1
    fi
    rm -f "$PIDFILE"
else
    say "aucune instance VICE enregistrée (pas de $PIDFILE)"
fi

if [ "$ALL" = 1 ]; then
    if pkill -u "$(id -u)" -TERM -x x64sc 2>/dev/null; then
        sleep 0.5
        pkill -u "$(id -u)" -KILL -x x64sc 2>/dev/null
        say "x64sc orphelins tués"
    fi
    pkill -u "$(id -u)" -TERM -f "xvfb-run -a .*x64sc" 2>/dev/null
fi
exit $rc
