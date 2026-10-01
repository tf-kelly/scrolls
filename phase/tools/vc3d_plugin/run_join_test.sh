#!/usr/bin/env bash
# Headless join-mode test of the plugin's menu handler (no VC3D, no adapter): builds SheetCheckController with Qt
# offscreen, triggers Tools -> Sheet check (joins) on the fixture's join spec, and checks what the real CLI produced.
# Usage: run_join_test.sh VC_SHEET_CHECK_PROGRAM [JOIN_SPEC]
#   VC_SHEET_CHECK_PROGRAM = the installed vc_sheet_check (pip install -e phase/tools/vc_sheet_check).
#   JOIN_SPEC defaults to join/fixture_A.json (fixture region A with its committed inputs; ~4 min, < 2 GB).
# Needs g++ and Qt6 Core + Widgets (qt6-base-dev); does not need VC3D.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); PROG=$1; SPEC=${2:-$HERE/join/fixture_A.json}; B=$(mktemp -d)
MOC=$(pkg-config --variable=libexecdir Qt6Core)/moc
"$MOC" "$HERE/src/SheetCheckController.hpp" -o "$B/moc_SheetCheckController.cpp"
g++ -std=c++20 -fPIC -Wall -Wextra -Werror -I"$HERE/src" "$HERE/src/test_sheet_check_controller.cpp" \
  "$HERE/src/SheetCheckController.cpp" "$HERE/src/SheetCheckCore.cpp" "$B/moc_SheetCheckController.cpp" \
  $(pkg-config --cflags --libs Qt6Widgets) -o "$B/test_sheet_check_controller"
XDG_CACHE_HOME="$B/cache" VC_SHEET_CHECK="$PROG" "$B/test_sheet_check_controller" "$SPEC"
