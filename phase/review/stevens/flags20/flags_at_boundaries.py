"""VP-M48 / SCALE-M36 item 20 (descriptive, post hoc, not registered): did the index's contradiction flags fire at the
confirmed boundaries of Stevens' pages 0 and 2?
  flags_at_boundaries.py PAGES_DIR D1_MAIN_JSON TRANCHE_TGZ WRAP_INDEX UNSATISFIED_CSV OUT_JSON
- Boundary points: every D1 main-boundary piece point of the page (page grid rc -> page xyz). Control points: the same
  number of random page vertices >= 30 vox (7.5 cells) from any main-boundary piece.
- A patch "touches" a point set if any of its valid vertices lies within 6 vox of a point.
- Flag: a join with >= 1 unsatisfied term (unsatisfied.csv). Reported: patches touching each set; how many carry any
  unsatisfied join; unsatisfied joins with both patches touching the set.
"""
import csv, io, json, sys, tarfile
import numpy as np, tifffile
from scipy import ndimage
from scipy.spatial import cKDTree
pages, d1p, tgz, widx, unsat, outp = sys.argv[1:7]; rng = np.random.default_rng(20260935)
D1 = {p["page"]: p for p in json.load(open(d1p))["pages"]}
sets = {}
for k in (0, 2):
    P = np.stack([tifffile.imread(f"{pages}/patch_{k}/{c}.tif").astype(np.float64) for c in "xyz"], -1); ok = (P[..., 0] > 0) & (P[..., 2] > 0)
    pts = np.concatenate([np.array(pl) for pl in D1[k]["polylines_rowcol"]]); rc = np.round(pts).astype(int)
    rc = rc[(rc[:, 0] >= 0) & (rc[:, 0] < ok.shape[0]) & (rc[:, 1] >= 0) & (rc[:, 1] < ok.shape[1])]; rc = rc[ok[rc[:, 0], rc[:, 1]]]
    B = np.zeros(ok.shape, bool); B[rc[:, 0], rc[:, 1]] = True; far = (ndimage.distance_transform_edt(~B) >= 7.5) & ok
    fr, fc = np.nonzero(far); s = rng.choice(len(fr), len(rc), replace=False)
    sets[f"p{k}_boundary"] = P[rc[:, 0], rc[:, 1]]; sets[f"p{k}_control"] = P[fr[s], fc[s]]
trees = {n: cKDTree(v) for n, v in sets.items()}; touch = {n: set() for n in sets}
idx = {ln.split(",")[0] for ln in open(widx).read().splitlines()[1:]}; buf = {}
lo = np.min([v.min(0) for v in sets.values()], 0) - 10; hi = np.max([v.max(0) for v in sets.values()], 0) + 10
with tarfile.open(tgz, "r|gz") as tf:
    for mem in tf:
        p = mem.name.split("/")
        if not mem.isfile() or p[-1] not in ("x.tif", "y.tif", "z.tif") or p[-2] not in idx: continue
        buf.setdefault(p[-2], {})[p[-1][0]] = tifffile.imread(io.BytesIO(tf.extractfile(mem).read())).astype(np.float64)
        if len(buf[p[-2]]) == 3:
            Bf = buf.pop(p[-2]); X = np.stack([Bf["x"], Bf["y"], Bf["z"]], -1).reshape(-1, 3); X = X[(X[:, 0] > 0) & (X[:, 2] > 0)]
            X = X[((X >= lo) & (X <= hi)).all(1)]
            if not len(X): continue
            for n, T in trees.items():
                if np.isfinite(T.query(X, distance_upper_bound=6.0)[0]).any(): touch[n].add(int(p[-2]))
joins = {}
for r in csv.DictReader(open(unsat)):
    a, b = int(r["patch_a"]), int(r["patch_b"]); joins[tuple(sorted((a, b)))] = True
flagged = {p for pr in joins for p in pr}
out = {"method": __doc__.strip().splitlines()[0], "points": {n: int(len(v)) for n, v in sets.items()}, "sets": {}}
for n, S in touch.items():
    inside = sum(1 for (a, b) in joins if a in S and b in S)
    out["sets"][n] = {"patches_touching": len(S), "patches_with_any_unsatisfied_join": len(S & flagged),
                      "share_flagged": round(len(S & flagged) / len(S), 3) if S else None, "unsatisfied_joins_within_set": inside}
json.dump(out, open(outp, "w"), indent=1); print(json.dumps(out, indent=1))
