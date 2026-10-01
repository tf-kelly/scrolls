#!/usr/bin/env bash
# Non-GUI tests. Usage: run_unit_tests.sh GOLDEN_OUT_DIR PYTHON
#   GOLDEN_OUT_DIR = output of phase/tools/example_outputs.py (fixture v1.1 region A); PYTHON per phase/tools/requirements.txt.
# Needs g++ and Qt6Core (qt6-base-dev); does not need VC3D.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); G=$1; PY=$2; B=$(mktemp -d)
g++ -std=c++20 -fPIC -Wall -Wextra -Werror "$HERE/src/test_sheet_check_core.cpp" "$HERE/src/SheetCheckCore.cpp" \
  $(pkg-config --cflags --libs Qt6Core) -o "$B/test_sheet_check_core"
"$B/test_sheet_check_core" "$G"
"$PY" "$HERE/test_overlay_vc3d_view.py"
"$PY" "$HERE/bridge_script/test_sheet_check_core.py" "$G"
