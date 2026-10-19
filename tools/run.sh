#!/usr/bin/env bash
# run.sh - lance un .prg dans VICE x64sc, visible (WSLg) ou headless (xvfb).
#
# Usage : run.sh [--show|--headless] [--warp] [--cycles N] [--screenshot f.png]
#                [--monitor] [--port P] [--wait] [--] prog.prg
#
#   --show        fenêtre VICE visible via WSLg (défaut)
#   --headless    sous xvfb-run, son désactivé, invisible
#   --warp        vitesse maximale (-warp)
#   --cycles N    -limitcycles N : VICE s'arrête seul après N cycles ;
#                 run.sh attend alors la fin (exécution bornée)
#   --screenshot  -exitscreenshot : capture PNG à la sortie (avec --cycles)
#   --monitor     -binarymonitor (port 6502) + -remotemonitor (port 6510),
#                 charge build/<prog>.labels via -moncommands, et attend
#                 que le port du moniteur binaire réponde avant de rendre la main
#   --port P      port du moniteur binaire (défaut 6502 ; texte = P+8)
#   --wait        attendre la fin de VICE même sans --cycles
#
# Sans --cycles ni --wait, VICE tourne en arrière-plan : son PID est écrit
# dans build/vice.pid et tools/stop.sh l'arrête. Une instance précédente
# encore vivante est arrêtée d'abord (une seule instance à la fois).
#
# Autostart : -autostart avec -autostartprgmode 1 (injection directe en RAM).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/build"
PIDFILE="$BUILD/vice.pid"
LOGFILE="$BUILD/vice.log"
X64SC="${X64SC:-x64sc}"

MODE=show
WARP=0
CYCLES=""
SCREENSHOT=""
MONITOR=0
PORT=6502
WAIT=0
PRG=""

die() { echo "run.sh: $*" >&2; exit 1; }
usage() { sed -n '2,24p' "$0"; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --show) MODE=show ;;
        --headless) MODE=headless ;;
        --warp) WARP=1 ;;
        --cycles) [ $# -ge 2 ] || die "--cycles attend un nombre"; CYCLES="$2"; shift ;;
        --screenshot) [ $# -ge 2 ] || die "--screenshot attend un fichier"; SCREENSHOT="$2"; shift ;;
        --monitor) MONITOR=1 ;;
        --port) [ $# -ge 2 ] || die "--port attend un nombre"; PORT="$2"; shift ;;
        --wait) WAIT=1 ;;
        -h|--help) usage 0 ;;
        --) shift; [ $# -ge 1 ] && PRG="$1"; break ;;
        -*) die "option inconnue : $1 (voir --help)" ;;
        *) [ -z "$PRG" ] || die "un seul programme à la fois"; PRG="$1" ;;
    esac
    shift
done

[ -n "$PRG" ] || usage 1
# Accepte "hello" comme raccourci de build/hello.prg.
if [ ! -f "$PRG" ] && [ -f "$BUILD/$PRG.prg" ]; then PRG="$BUILD/$PRG.prg"; fi
[ -f "$PRG" ] || die "programme introuvable : $PRG"
PRG="$(cd "$(dirname "$PRG")" && pwd)/$(basename "$PRG")"
[[ "$CYCLES" =~ ^[0-9]*$ ]] || die "--cycles : nombre attendu, reçu '$CYCLES'"
[[ "$PORT" =~ ^[0-9]+$ ]] || die "--port : nombre attendu, reçu '$PORT'"
[ -n "$SCREENSHOT" ] && [ -z "$CYCLES" ] && die "--screenshot nécessite --cycles N"
command -v "$X64SC" >/dev/null || die "x64sc introuvable : lancez tools/install.sh"

mkdir -p "$BUILD"
NAME="$(basename "${PRG%.prg}")"
LABELS="${PRG%.prg}.labels"

# Une seule instance : on arrête la précédente proprement.
"$ROOT/tools/stop.sh" --quiet || true

ARGS=(-default -autostartprgmode 1 -autostart "$PRG")
# Options supplémentaires passées telles quelles à x64sc (ex. VICE_EXTRA_ARGS="-ntsc").
# shellcheck disable=SC2206
[ -n "${VICE_EXTRA_ARGS:-}" ] && ARGS+=($VICE_EXTRA_ARGS)
[ "$WARP" = 1 ] && ARGS+=(-warp)
[ -n "$CYCLES" ] && ARGS+=(-limitcycles "$CYCLES")
if [ -n "$SCREENSHOT" ]; then
    SCREENSHOT="$(cd "$(dirname "$SCREENSHOT")" 2>/dev/null && pwd || die "répertoire de capture inexistant : $(dirname "$SCREENSHOT")")/$(basename "$SCREENSHOT")"
    rm -f "$SCREENSHOT"
    ARGS+=(-exitscreenshot "$SCREENSHOT")
fi
if [ "$MONITOR" = 1 ]; then
    ARGS+=(-binarymonitor -binarymonitoraddress "ip4://127.0.0.1:$PORT"
           -remotemonitor -remotemonitoraddress "ip4://127.0.0.1:$((PORT + 8))")
    if [ -f "$LABELS" ]; then
        ARGS+=(-moncommands "$LABELS")
        # dbg.py cherche par défaut build/vice.labels = labels du programme courant.
        cp -f "$LABELS" "$BUILD/vice.labels"
    else
        echo "run.sh: pas de fichier de labels $LABELS (make ?)" >&2
        rm -f "$BUILD/vice.labels"
    fi
fi

case "$MODE" in
    headless)
        ARGS+=(-sounddev dummy)
        # GDK préfère Wayland si WAYLAND_DISPLAY est défini : on force X11 pour
        # que la fenêtre aille bien dans le X virtuel et pas sur le bureau.
        CMD=(env -u WAYLAND_DISPLAY GDK_BACKEND=x11 xvfb-run -a "$X64SC" "${ARGS[@]}")
        ;;
    show)
        [ -n "${DISPLAY:-}" ] || die "DISPLAY non défini : WSLg inactif ? (utilisez --headless)"
        CMD=(env -u WAYLAND_DISPLAY GDK_BACKEND=x11 "$X64SC" "${ARGS[@]}")
        ;;
esac

echo "run.sh: $NAME ($MODE$( [ "$MONITOR" = 1 ] && echo ", monitor :$PORT")$( [ -n "$CYCLES" ] && echo ", $CYCLES cycles"))"
: >"$LOGFILE"
# setsid : VICE (et xvfb-run) forment leur propre groupe de processus, que
# stop.sh peut tuer d'un bloc.
setsid "${CMD[@]}" </dev/null >>"$LOGFILE" 2>&1 &
VICE_PID=$!
echo "$VICE_PID" >"$PIDFILE"

if [ "$MONITOR" = 1 ]; then
    # Attend l'ouverture du port du moniteur binaire (VICE l'ouvre au démarrage).
    for _ in $(seq 1 100); do
        if nc -z 127.0.0.1 "$PORT" 2>/dev/null; then break; fi
        kill -0 "$VICE_PID" 2>/dev/null || { tail -5 "$LOGFILE" >&2; die "VICE s'est arrêté avant d'ouvrir le moniteur (voir $LOGFILE)"; }
        sleep 0.1
    done
    nc -z 127.0.0.1 "$PORT" 2>/dev/null || die "le moniteur binaire ne répond pas sur le port $PORT"
    echo "run.sh: moniteur binaire prêt sur 127.0.0.1:$PORT (texte : $((PORT + 8)))"
    # Démon dbg.py : garde une connexion permanente à VICE (sinon VICE
    # repart dès qu'un client se déconnecte et se fige sur un point d'arrêt
    # atteint sans client). Voir l'en-tête de tools/dbg.py.
    DBG_SOCK="${C64_DBG_SOCK:-$BUILD/dbg.sock}"
    rm -f "$DBG_SOCK"
    setsid python3 "$ROOT/tools/dbg.py" --port "$PORT" --sock "$DBG_SOCK" --daemon \
        </dev/null >>"$BUILD/dbg.log" 2>&1 &
    echo "$!" >"$BUILD/dbg.pid"
    for _ in $(seq 1 50); do
        [ -S "$DBG_SOCK" ] && break
        sleep 0.1
    done
    [ -S "$DBG_SOCK" ] || die "le démon dbg.py n'a pas démarré (voir $BUILD/dbg.log)"
fi

if [ -n "$CYCLES" ] || [ "$WAIT" = 1 ]; then
    set +e
    wait "$VICE_PID"
    rc=$?
    set -e
    rm -f "$PIDFILE"
    if [ -n "$CYCLES" ]; then
        # -limitcycles fait sortir VICE avec le code 1 : c'est le cas normal.
        if grep -q "cycle limit reached" "$LOGFILE"; then
            [ -z "$SCREENSHOT" ] || [ -s "$SCREENSHOT" ] || die "capture absente : $SCREENSHOT"
            echo "run.sh: terminé après $CYCLES cycles${SCREENSHOT:+, capture $SCREENSHOT}"
            exit 0
        fi
        tail -5 "$LOGFILE" >&2
        die "VICE s'est terminé anormalement (rc=$rc), voir $LOGFILE"
    fi
    exit $rc
fi

echo "run.sh: VICE en arrière-plan, PID $VICE_PID (tools/stop.sh pour l'arrêter)"
