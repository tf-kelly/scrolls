"""D1 supplement: the raw per-vertex boundary is fragmented (speckled q), so the main boundary is taken on a smoothed
map: (q == modal) on valid vertices, majority over a 15 x 15 cell window (60 voxels; uniform_filter of the indicator and
of validity, ratio > 0.5). Reported: connected minority regions (4-conn) of the smoothed map with area >= 0.5 cm^2
(area, centroid row/col), main boundary edges between smoothed classes (length) and their polylines (as d1_boundaries.py).
The raw minority area stays the D1 figure; this only locates where the boundary is coherent.
  d1_main.py DUMP_DIR PAGES_DIR OUT.json
"""
import json, os, sys
import numpy as np, tifffile
from scipy import ndimage
from scipy.spatial import cKDTree
VOX_CM2 = (7.91e-4) ** 2; CELL = 16 * VOX_CM2
dump, pages, outp = sys.argv[1:4]; out = {"rule": "15x15 majority smoothing of (q == modal)", "pages": []}


def chain(Q):
    T = cKDTree(Q); used = np.zeros(len(Q), bool); cur = int(np.argmin(Q[:, 0] + Q[:, 1])); order = [cur]; used[cur] = True
    for _ in range(len(Q) - 1):
        _, j = T.query(Q[cur], k=min(16, len(Q)))
        nxt = next((int(x) for x in np.atleast_1d(j) if not used[x]), None)
        if nxt is None: nxt = int(np.nonzero(~used)[0][np.argmin(((Q[~used] - Q[cur]) ** 2).sum(1))])
        used[nxt] = True; order.append(nxt); cur = nxt
    return Q[order]


for k in (0, 1, 2, 5):
    z = np.load(os.path.join(dump, f"patch_{k}_q.npz")); ii, jj, q, m = z["ii"], z["jj"], z["q"], z["matched"]
    H, W = tifffile.imread(f"{pages}/patch_{k}/x.tif").shape
    vals, cnt = np.unique(q[m], return_counts=True); qmod = int(vals[np.argmax(cnt)])
    V = np.zeros((H, W)); V[ii, jj] = 1; I = np.zeros((H, W)); I[ii, jj] = (q == qmod)
    fr = ndimage.uniform_filter(I, 15) / np.maximum(ndimage.uniform_filter(V, 15), 1e-9)
    S = np.full((H, W), -1, np.int8); S[ii, jj] = (fr[ii, jj] > 0.5)
    lab, n = ndimage.label(S == 0)
    regs = []
    for i in range(1, n + 1):
        rr, cc = np.nonzero(lab == i); a = len(rr) * CELL
        if a >= 0.5: regs.append({"area_cm2": round(a, 2), "centroid_rowcol": [round(float(rr.mean()), 1), round(float(cc.mean()), 1)]})
    pts = []
    for (dr, dc) in ((1, 0), (0, 1)):
        A, B = S[:H - dr, :W - dc], S[dr:, dc:]; r, c = np.nonzero((A >= 0) & (B >= 0) & (A != B))
        pts.append(np.stack([r + dr / 2, c + dc / 2], 1))
    P = np.concatenate(pts)
    lat = np.zeros((2 * H, 2 * W), bool); lat[(2 * P[:, 0]).astype(int), (2 * P[:, 1]).astype(int)] = True
    lab2, n2 = ndimage.label(ndimage.binary_dilation(lat, np.ones((3, 3))), structure=np.ones((3, 3))); ids = lab2[(2 * P[:, 0]).astype(int), (2 * P[:, 1]).astype(int)]
    pieces = sorted([P[ids == i] for i in range(1, n2 + 1)], key=len, reverse=True)
    polys = [chain(Q) for Q in pieces if len(Q) >= 50]
    out["pages"].append({"page": k, "modal_q": qmod, "smoothed_minority_area_cm2": round(float((S == 0).sum() * CELL), 2),
                         "minority_regions_ge_0p5cm2": sorted(regs, key=lambda r: -r["area_cm2"]),
                         "main_boundary_length_mm": round(len(P) * 4 * 7.91e-3, 1),
                         "polylines_ge_50pts": len(polys), "longest_polyline_mm": round(len(pieces[0]) * 4 * 7.91e-3, 1) if pieces else 0,
                         "polylines_rowcol": [np.round(Q, 1).tolist() for Q in polys]})
    p = out["pages"][-1]; print({x: (p[x] if x != "minority_regions_ge_0p5cm2" else p[x][:5]) for x in p if x != "polylines_rowcol"}, flush=True)
json.dump(out, open(outp, "w"))
