#!/usr/bin/env bash
# Usage: run_axis.sh VC3D WORK_DIR OUT CASE SHEET_CHECK_BIN_DIR AXIS_CSV   (CASE A | B | C; SHEET_CHECK_BIN_DIR holds SessA's vc_sheet_check)
set -u
VC3D=$1; W=$2; OUT=$3; CASE=$4; V1D=$5; AX=$6; HERE=$(cd "$(dirname "$0")" && pwd)
rm -rf "$OUT"; mkdir -p "$OUT/cfg"; printf '[project]\nshow_open_data_catalog_on_startup=false\n' > "$OUT/cfg/VC3D.ini"
export DISPLAY=${DISPLAY:-:99}
pgrep -x Xvfb >/dev/null || { Xvfb "$DISPLAY" -screen 0 1920x1080x24 >/dev/null 2>&1 & sleep 2; }
rm -f /tmp/vc3d-inapp
VC3D_CONFIG_DIR="$OUT/cfg" XDG_CACHE_HOME="$OUT/cache" VC_SHEET_CHECK="$V1D/vc_sheet_check" VC_SHEET_CHECK_NO_DIALOGS=1 \
  QT_QPA_PLATFORM=xcb "$VC3D" --agent-bridge-name vc3d-inapp > "$OUT/vc3d.log" 2>&1 &
PID=$!
timeout 1200 python3 "$HERE/axis_test.py" "$W/cfx" "$OUT" "$CASE" "$AX"; RC=$?
kill $PID 2>/dev/null; wait $PID 2>/dev/null
exit $RC
