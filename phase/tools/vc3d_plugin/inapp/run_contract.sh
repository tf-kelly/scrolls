#!/usr/bin/env bash
# In-app test of Tools -> Sheet check under Xvfb, driven by VC3D's agent bridge and xdotool.
# The CLI is STUBBED (stub_contract_cli replays golden contract outputs; it does no analysis).
# Usage: run_contract.sh VC3D_BINARY WORK_DIR OUT_DIR MODE PYTHON
#   WORK_DIR from build_inapp_fixture.sh; MODE plain | view | clusters | plain_clusters;
#   PYTHON with zarr (used by the stub to write overlay_vc3d.zarr).
set -u
VC3D=$1; W=$2; OUT=$3; MODE=$4; PY=$5; HERE=$(cd "$(dirname "$0")" && pwd)
rm -rf "$OUT"; mkdir -p "$OUT/cfg"
printf '[project]\nshow_open_data_catalog_on_startup=false\n' > "$OUT/cfg/VC3D.ini"  # no catalog fetch
export DISPLAY=${DISPLAY:-:99}
pgrep -x Xvfb >/dev/null || { Xvfb "$DISPLAY" -screen 0 1920x1080x24 >/dev/null 2>&1 & sleep 2; }
rm -f /tmp/vc3d-inapp
VC3D_CONFIG_DIR="$OUT/cfg" XDG_CACHE_HOME="$OUT/cache" VC_SHEET_CHECK="$HERE/stub_contract_cli" \
  STUB_GOLDEN="$W/golden/A" STUB_MODE="$MODE" VP_TOOLS="$HERE/.." VP_PY="$PY" \
  VC_SHEET_CHECK_NO_DIALOGS=1 QT_QPA_PLATFORM=xcb \
  "$VC3D" --agent-bridge-name vc3d-inapp > "$OUT/vc3d.log" 2>&1 &
PID=$!
timeout 240 python3 "$HERE/inapp_contract.py" "$W/cfx" "$OUT" "$MODE"; RC=$?
kill $PID 2>/dev/null; wait $PID 2>/dev/null
grep 'vc.sheet_check:\|stub_contract_cli' "$OUT/vc3d.log"
exit $RC
