"""Check that probe controls (overlay off) show CT at the right place (SessD-5 (3)).
Usage: eval_controls.py PROBE_RESULT_JSON CT_U8_ZARR
For every control capture: its 4 pixels must be gray (r=g=b) and not black. In the xy viewer (v2; screen x = +x,
screen y = +y, 128 px/voxel) each pixel's volume point is focus + (dx, dy)/scale, and the gray must match the uint8
CT trilinearly interpolated there (VC3D samples the base volume trilinear: CChunkedVolumeViewer.hpp:413), to 3 gray levels."""
import json, sys
import numpy as np, zarr
r = json.load(open(sys.argv[1])); ct = zarr.open_array(sys.argv[2] + "/0", mode="r")
def tri(z, y, x):
    z0, y0, x0 = int(np.floor(z)), int(np.floor(y)), int(np.floor(x))
    blk = ct[z0:z0 + 2, y0:y0 + 2, x0:x0 + 2].astype(float); fz, fy, fx = z - z0, y - y0, x - x0
    wz, wy, wx = np.array([1 - fz, fz]), np.array([1 - fy, fy]), np.array([1 - fx, fx])
    return float(np.einsum("i,j,k,ijk->", wz, wy, wx, blk))
out = {"controls": 0, "gray_not_black": 0, "xy_pixels": 0, "xy_match_3": 0, "rows": []}
OFF = [(25, 25), (-25, 25), (25, -25), (-25, -25)]            # probe_inapp.py's pixel offsets, in this order
for c in r["captures"]:
    if c["pass"] != "control" or c.get("hidden"): continue
    out["controls"] += 1
    gray = [p[0] == p[1] == p[2] and p[0] > 0 for p in c["rgb"]]
    out["gray_not_black"] += all(gray)
    row = {"name": c["name"], "viewer": c["viewer"], "rgb": c["rgb"], "gray_not_black": all(gray)}
    if c["viewer"] == "v2":
        z, y, x = [v + 0.25 for v in c["voxel_scan_zyx"]]
        exp = [tri(z, y + dy / 128.0, x + dx / 128.0) for dx, dy in OFF]
        got = [p[0] for p in c["rgb"]]
        row["expected_trilinear"] = [round(e, 1) for e in exp]
        out["xy_pixels"] += 4; out["xy_match_3"] += sum(abs(g - e) <= 3 for g, e in zip(got, exp))
    out["rows"].append(row)
print(json.dumps({k: v for k, v in out.items() if k != "rows"}))
json.dump(out, open(sys.argv[1].replace(".json", "_controls.json"), "w"), indent=1)
