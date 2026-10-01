#!/usr/bin/env bash
# Usage: run_project_entries.sh VC3D WORK_DIR OUT PYTHON
set -u
VC3D=$1; W=$2; OUT=$3; PY=$4; HERE=$(cd "$(dirname "$0")" && pwd)
rm -rf "$OUT"; mkdir -p "$OUT/cfg"; printf '[project]\nshow_open_data_catalog_on_startup=false\n' > "$OUT/cfg/VC3D.ini"
export DISPLAY=${DISPLAY:-:99}
pgrep -x Xvfb >/dev/null || { Xvfb "$DISPLAY" -screen 0 1920x1080x24 >/dev/null 2>&1 & sleep 2; }
rm -f /tmp/vc3d-inapp
VC3D_CONFIG_DIR="$OUT/cfg" XDG_CACHE_HOME="$OUT/cache" VC_SHEET_CHECK="$HERE/stub_contract_cli" \
  STUB_GOLDEN="$W/golden/A" STUB_MODE=golden VP_TOOLS="$HERE/.." VP_PY="$PY" \
  VC_SHEET_CHECK_NO_DIALOGS=1 QT_QPA_PLATFORM=xcb "$VC3D" --agent-bridge-name vc3d-inapp > "$OUT/vc3d.log" 2>&1 &
PID=$!
timeout 300 python3 "$HERE/project_entries_test.py" "$W/cfx" "$OUT"; RC=$?
kill $PID 2>/dev/null; wait $PID 2>/dev/null
grep 'vc.sheet_check:' "$OUT/vc3d.log" | grep -v 'start ' | sed "s|$OUT|<run>|g"
exit $RC
