"""Build a placement probe for an EXISTING full-frame overlay, without copying it.

Usage: probe_existing.py OVERLAY_ZARR OUT_DIR [--per-value 2] [--within Z0 Y0 X0 Z1 Y1 X1]
Reads level 0 of OVERLAY_ZARR (only the stored chunk files, so a sparse full-frame array is cheap), picks
--per-value voxels of value 1 and of value 2 that have a value-0 face neighbour (deterministic: evenly spaced
through the sorted boundary voxels; with --within, only voxels whose pair lies 2 voxels inside [lo, hi), e.g. where a
local CT exists so the overlay-off controls show CT), and writes
  OUT_DIR/report.json   one "cluster" per test voxel (the voxel and its 0-neighbour), centroid = voxel + 0.25,
                        with "probe_expect" = the value the overlay itself holds there
  OUT_DIR/overlay.zarr  a SYMLINK to OVERLAY_ZARR, so VC3D and the plugin's guard read the producer's own files.
The in-app side is run_probe.sh with PROBE_DIR=dirname(OUT_DIR), VARIANT=basename(OUT_DIR).
"""
import argparse, json, os
import numpy as np, zarr

ap = argparse.ArgumentParser(); ap.add_argument("overlay"); ap.add_argument("out"); ap.add_argument("--per-value", type=int, default=2)
ap.add_argument("--within", type=int, nargs=6, default=None)
a = ap.parse_args()
src = os.path.realpath(a.overlay)
arr = zarr.open_array(os.path.join(src, "0"), mode="r")
meta = json.load(open(os.path.join(src, "0", ".zarray")))
sep = meta.get("dimension_separator", "."); ch = np.array(meta["chunks"])
keys = []
for d, _, fs in os.walk(os.path.join(src, "0")):
    for f in fs:
        if f.startswith("."): continue
        rel = os.path.relpath(os.path.join(d, f), os.path.join(src, "0"))
        keys.append(tuple(int(p) for p in (rel.split(os.sep) if sep == "/" else rel.split("."))))
E = [np.array(e) for e in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
def val(t):
    t = np.asarray(t)
    return int(arr[t[0], t[1], t[2]]) if np.all(t >= 0) and np.all(t < arr.shape) else 0
tests = []
box = (np.array(a.within[:3]) + 2, np.array(a.within[3:]) - 2) if a.within else None
def inside(t): return box is None or (np.all(t >= box[0]) and np.all(t < box[1]))
for v in (1, 2):
    cand = []
    for k in sorted(keys):
        lo = np.array(k) * ch
        if box is not None and (np.any(lo + ch <= box[0]) or np.any(lo >= box[1])): continue
        blk = arr[lo[0]:lo[0]+ch[0], lo[1]:lo[1]+ch[1], lo[2]:lo[2]+ch[2]]
        for idx in np.argwhere(blk == v):
            t = lo + idx
            if not inside(t): continue
            for e in E:
                if inside(t + e) and val(t + e) == 0:
                    cand.append((t, t + e)); break
    if not cand:
        print(f"no boundary voxel of value {v}"); continue
    for j in np.linspace(0, len(cand) - 1, a.per_value).round().astype(int):
        t, n = cand[j]
        tests += [(f"V{v}_{len(tests)}", t, v), (f"V{v}_{len(tests)}_zero_nb", n, 0)]
os.makedirs(a.out, exist_ok=True)
cl = [{"id": i, "kind": "suspect_join", "n_pairs": 0, "n_patches": 0, "area_cm2": 0.0,
       "centroid_zyx": (t + 0.25).astype(float).tolist(), "bbox_zyx": [t.tolist(), t.tolist()],
       "theta_deg": 0.0, "wrap_index_range": [0, 0], "patches": [], "pairs": [], "max_risk": None,
       "probe_name": name, "probe_expect": exp, "probe_voxel_scan_zyx": t.tolist()}
      for i, (name, t, exp) in enumerate(tests)]
json.dump({"contract": "v1", "status": "ok", "git": "probe", "branch": "<branch> (placement probe of an existing overlay)",
           "region": {"origin_zyx": [0, 0, 0], "shape_zyx": list(arr.shape)}, "inputs": {"overlay": src},
           "counts": {"pairs_flagged": 0}, "clusters": cl}, open(os.path.join(a.out, "report.json"), "w"), indent=1)
link = os.path.join(a.out, "overlay.zarr")
if os.path.lexists(link): os.remove(link)
os.symlink(src, link)
print(json.dumps({"overlay": src, "stored_level0_chunks": len(keys), "tests": [(n, t.tolist(), e) for n, t, e in tests]}))
