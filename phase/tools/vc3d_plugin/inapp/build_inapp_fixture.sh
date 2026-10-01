#!/usr/bin/env bash
# Build the in-app test inputs from committed data. Usage: build_inapp_fixture.sh WORK_DIR PYTHON
#   PYTHON must satisfy phase/tools/requirements.txt (zarr==2.18.7, Amendment 4 A4.5).
# Writes WORK_DIR/golden/A   (phase/tools/example_outputs.py, current fixture region A: v1.4 at this commit)
#        WORK_DIR/cfx/volumes/ct_A_view.zarr   (fixture CT relocated to the scan frame)
#        WORK_DIR/cfx/paths/patch_150217       (fixture patch, byte-identical to patches.zip)
#        WORK_DIR/cfx/umbilicus.json           (contract axis in villa's layout; SessD-5)
#        WORK_DIR/cfx/volumes/ct_A_u8.zarr     (fixture CT as uint8, levels 0-1; SessD-5)
set -euo pipefail
W=$1; PY=$2; HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../../../.." && pwd)
rm -rf "$W/golden/A" "$W/cfx"; mkdir -p "$W/golden" "$W/cfx/volumes" "$W/cfx/paths"
"$PY" "$REPO/phase/tools/example_outputs.py" "$W/golden/A"
"$PY" "$REPO/phase/tools/test_fixture.py" --outputs "$W/golden/A" | tail -1
"$PY" "$HERE/../overlay_vc3d_view.py" "$REPO/phase/data_small/fixture/ct.zarr" "$W/cfx/volumes/ct_A_view.zarr" \
  --scan-shape 11174 3340 3440 --uuid fixture_ct_A --name "fixture CT region A (view)"
"$PY" "$HERE/pick_targets.py" "$W/golden/A" --check
( cd "$W/cfx/paths" && unzip -q "$REPO/phase/data_small/fixture/patches.zip" 's4_good_patches/patch_150217/*' \
  && mv s4_good_patches/patch_150217 . && rmdir s4_good_patches )
# The plugin needs the scan's umbilicus for --axis-file (SessD-5, contract A5.3); VC3D's discovery finds <root>/umbilicus.json.
"$PY" - "$REPO/phase/tools/axis/pherc1667_x3slab2_axis.csv" "$W/cfx/umbilicus.json" <<'PYEOF'
import json, sys
pts = [[float(v) for v in l.split(",")] for l in open(sys.argv[1]) if l.strip() and not l.startswith("z")]
json.dump({"points": pts}, open(sys.argv[2], "w"))     # villa layout: [z, y, x] per point
PYEOF
"$PY" "$HERE/make_ct_u8.py" "$W/cfx/volumes/ct_A_u8.zarr"
echo "in-app fixture ready in $W"
