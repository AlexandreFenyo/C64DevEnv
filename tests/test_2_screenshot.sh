#!/usr/bin/env bash
# Test 2 : hello.prg en headless avec limite de cycles et capture d'écran ;
# le PNG doit exister et ne pas être uniforme (ni tout noir).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

PNG="build/test_hello.png"
CYCLES=5000000
rm -f "$PNG"

[ -f build/hello.prg ] || make >/dev/null || { echo "ECHEC : build"; exit 1; }
if ! tools/run.sh --headless --warp --cycles "$CYCLES" --screenshot "$PNG" build/hello.prg; then
    echo "ECHEC : run.sh"
    exit 1
fi
[ -s "$PNG" ] || { echo "ECHEC : capture $PNG absente"; exit 1; }
identify "$PNG" >/dev/null 2>&1 || { echo "ECHEC : $PNG n'est pas une image valide"; exit 1; }

# Écart-type et moyenne normalisés [0,1] : une image uniformément noire
# donne std=0 et mean=0.
read -r std mean < <(convert "$PNG" -format "%[fx:standard_deviation] %[fx:mean]" info:)
echo "capture : $(identify -format '%wx%h' "$PNG"), std=$std mean=$mean"
awk -v s="$std" -v m="$mean" 'BEGIN { exit !(s > 0.01 && m > 0.01) }' \
    || { echo "ECHEC : image uniforme ou noire"; exit 1; }

# La bordure doit être verte (hello.s écrit 5 dans $D020) : pixel (2,2),
# composante verte dominante.
read -r r g b < <(convert "$PNG" -format '%[fx:int(255*p{2,2}.r)] %[fx:int(255*p{2,2}.g)] %[fx:int(255*p{2,2}.b)]' info:)
echo "bordure : rgb($r,$g,$b)"
[ "$g" -gt "$r" ] && [ "$g" -gt "$b" ] && [ "$g" -gt 100 ] \
    || { echo "ECHEC : bordure non verte, le programme n'a pas tourné ?"; exit 1; }
echo "Screenshot OK"
