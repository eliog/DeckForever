#!/usr/bin/env bash
# Runs the offline test suite on any machine (macOS or Linux). Nothing touches your real Steam install.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
cd "$ROOT"
echo "== steam_shortcuts"; python3 -I tests/test_steam_shortcuts.py
echo "== engine";          python3 -I tests/test_engine.py
echo "ALL TESTS PASSED"
