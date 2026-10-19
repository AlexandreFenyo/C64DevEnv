#!/usr/bin/env bash
# Test 4 : portail de développement (tools/portal.py), de bout en bout via
# HTTP, et cohérence entre les outils et le portail (registre de portal.py).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
exec python3 tests/portal_test.py
