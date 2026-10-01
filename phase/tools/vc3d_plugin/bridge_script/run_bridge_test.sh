#!/usr/bin/env bash
# Usage: run_bridge_test.sh VC3D WORK_DIR OUT MODE PYTHON_WITH_ZARR
set -u
VC3D=$1; W=$2; OUT=$3; MODE=$4; PY=$5; HERE=$(cd "$(dirname "$0")" && pwd)
rm -rf "$OUT"; mkdir -p "$OUT/cfg"; printf '[project]\nshow_open_data_catalog_on_startup=false\n' > "$OUT/cfg/VC3D.ini"
export DISPLAY=${DISPLAY:-:99}
pgrep -x Xvfb >/dev/null || { Xvfb "$DISPLAY" -screen 0 1920x1080x24 >/dev/null 2>&1 & sleep 2; }
rm -f /tmp/vc3d-inapp
VC3D_CONFIG_DIR="$OUT/cfg" QT_QPA_PLATFORM=xcb "$VC3D" --agent-bridge-name vc3d-inapp > "$OUT/vc3d.log" 2>&1 &
PID=$!
timeout 400 python3 "$HERE/bridge_inapp_test.py" "$W" "$OUT" "$MODE" "$PY"; RC=$?
kill $PID 2>/dev/null; wait $PID 2>/dev/null
exit $RC
