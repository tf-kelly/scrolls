#!/usr/bin/env bash
# Usage: run_real.sh VC3D WORK_DIR OUT MODE SHEET_CHECK_TREE SHEET_CHECK_BIN   (MODE region | segment)
set -u
VC3D=$1; W=$2; OUT=$3; MODE=$4; V1T=$5; V1B=$6; HERE=$(cd "$(dirname "$0")" && pwd)
rm -rf "$OUT"; mkdir -p "$OUT/cfg"; printf '[project]\nshow_open_data_catalog_on_startup=false\n' > "$OUT/cfg/VC3D.ini"
export DISPLAY=${DISPLAY:-:99}
pgrep -x Xvfb >/dev/null || { Xvfb "$DISPLAY" -screen 0 1920x1080x24 >/dev/null 2>&1 & sleep 2; }
rm -f /tmp/vc3d-inapp
CLI="$(dirname "$V1B")/vc_sheet_check"; [ "$MODE" = region ] && CLI="$HERE/region_adapter.sh"
SHEET_CHECK_TREE="$V1T" SHEET_CHECK_BIN="$V1B" VC3D_CONFIG_DIR="$OUT/cfg" XDG_CACHE_HOME="$OUT/cache" VC_SHEET_CHECK="$CLI" \
  VC_SHEET_CHECK_NO_DIALOGS=1 QT_QPA_PLATFORM=xcb "$VC3D" --agent-bridge-name vc3d-inapp > "$OUT/vc3d.log" 2>&1 &
PID=$!
timeout 900 python3 "$HERE/real_region_test.py" "$W/cfx" "$OUT" "$MODE"; RC=$?
kill $PID 2>/dev/null; wait $PID 2>/dev/null
exit $RC
