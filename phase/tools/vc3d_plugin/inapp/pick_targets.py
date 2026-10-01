"""Derive the in-app test's segment and jump targets from committed fixture data.

- segment: the region-A patch whose vertices hit the most golden-overlay voxels of value 2
  (then value 1). Golden overlay = phase/tools/example_outputs.py region A.
Fixture v1.1: the golden overlay is full-frame (Amendment 4), so it is indexed in scan coordinates directly.
Prints JSON; with --check, asserts the segment the in-app tests use.
Usage: pick_targets.py GOLDEN_OUT_DIR [--check]
"""
import csv, io, json, os, sys, zipfile
import numpy as np, tifffile, zarr
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 4))
FIX = os.path.join(REPO, "phase/data_small/fixture")
golden = sys.argv[1]
o = np.array(json.load(open(os.path.join(golden, "report.json")))["region"]["origin_zyx"])
S = json.load(open(os.path.join(golden, "report.json")))["region"]["shape_zyx"]
ov = zarr.open_array(os.path.join(golden, "overlay.zarr", "0"), mode="r")[o[0]:o[0]+S[0], o[1]:o[1]+S[1], o[2]:o[2]+S[2]]
z = zipfile.ZipFile(os.path.join(FIX, "patches.zip")); names = z.namelist()
best = []
for r in csv.DictReader(open(os.path.join(FIX, "patches.csv"))):
    if "A" not in r["regions"]:
        continue
    pre = [n for n in names if n.endswith(f"/patch_{r['id']}/x.tif")]
    if not pre:
        continue
    d = pre[0][:-5]
    X, Y, Z = [tifffile.imread(io.BytesIO(z.read(d + c + ".tif"))) for c in "xyz"]
    m = X > 0
    p = np.stack([Z[m], Y[m], X[m]], 1) - o
    ok = np.all((p >= 0) & (p < ov.shape), 1)
    q = np.round(p[ok]).astype(int).clip(0, np.array(ov.shape) - 1)
    v = ov[q[:, 0], q[:, 1], q[:, 2]]
    best.append((int((v == 2).sum()), int((v == 1).sum()), r["id"], d))
best.sort(reverse=True)
out = {"patch": best[0][2], "zip_dir": best[0][3], "vertex_hits_v2_v1": best[0][:2]}
print(json.dumps(out))
if "--check" in sys.argv:
    assert out["patch"] == "150217", out
    print("segment matches the one the in-app tests use")
