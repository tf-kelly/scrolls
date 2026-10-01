#!/usr/bin/env bash
# Usage: [VP_SHOW_XZ=1] run_probe.sh VC3D WORK_DIR PROBE_DIR OUT VARIANT   (PROBE_DIR from make_probe.py / probe_existing.py)
set -u
VC3D=$1; W=$2; PD=$3; OUT=$4; V=$5; HERE=$(cd "$(dirname "$0")" && pwd)
rm -rf "$OUT"; mkdir -p "$OUT/cfg"; printf '[project]\nshow_open_data_catalog_on_startup=false\n' > "$OUT/cfg/VC3D.ini"
# VP_SHOW_XZ=1 un-hides the xz pane (VC3D's own layout setting; the default layout hides it, CWindow.cpp:888)
if [ "${VP_SHOW_XZ:-0}" = 1 ]; then printf '[mainWin]\nmain_viewer_layout_surfaces=segmentation, xy plane, seg xz, seg yz\nmain_viewer_layout_hidden=0, 0, 0, 0\n' >> "$OUT/cfg/VC3D.ini"; fi
export DISPLAY=${DISPLAY:-:99}
pgrep -x Xvfb >/dev/null || { Xvfb "$DISPLAY" -screen 0 1920x1080x24 >/dev/null 2>&1 & sleep 2; }
rm -f /tmp/vc3d-inapp
VC3D_CONFIG_DIR="$OUT/cfg" XDG_CACHE_HOME="$OUT/cache" VC_SHEET_CHECK="$HERE/stub_probe_cli" PROBE_SRC="$PD/$V" \
  VC_SHEET_CHECK_NO_DIALOGS=1 QT_QPA_PLATFORM=xcb "$VC3D" --agent-bridge-name vc3d-inapp > "$OUT/vc3d.log" 2>&1 &
PID=$!
timeout 600 python3 "$HERE/probe_inapp.py" "$W/cfx" "$OUT" "$V"; RC=$?
kill $PID 2>/dev/null; wait $PID 2>/dev/null
grep 'vc.sheet_check:' "$OUT/vc3d.log" | grep -v 'jump ' | sed 's|/root/[^ ]*sheet_check/|<cache>/|g'
exit $RC
