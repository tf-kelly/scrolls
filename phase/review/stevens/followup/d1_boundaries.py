"""Coordinator 02:09 D1: per page with >= 1 % of vertices off the modal sheet key (our index, SCALE quilt2 rule via the
VP dump): minority area (X1's rule, 16 vox^2 per vertex at scale 0.25), boundary length, boundary polylines in page
grid coordinates (row, col; one grid cell = 4 voxels). Sheet key q per vertex as quilt2 assigns it (radius-matched
vertices; others take the nearest matched vertex's winding). Boundary: every pair of 4-adjacent valid vertices with one on the
modal key and one off it is a boundary edge (length 4 voxels); its midpoint is a boundary point. Points are grouped into
pieces connected within one cell on the half-cell lattice (3x3 dilation, then 8-connectivity) and each piece is ordered into a polyline by nearest-neighbour chaining.
Pieces of < 8 points (specks) are dropped from the polylines and counted separately; length counts all edges.
  d1_boundaries.py DUMP_DIR PAGES_DIR OUT.json
"""
import json, os, sys
import numpy as np, tifffile
from scipy import ndimage
from scipy.spatial import cKDTree
VOX_CM2 = (7.91e-4) ** 2
dump, pages, outp = sys.argv[1:4]; out = {"rule": __doc__.strip().split("\n")[0], "pages": []}
for k in range(10):
    z = np.load(os.path.join(dump, f"patch_{k}_q.npz")); ii, jj, q, m = z["ii"], z["jj"], z["q"], z["matched"]
    H, W = tifffile.imread(f"{pages}/patch_{k}/x.tif").shape
    vals, cnt = np.unique(q[m], return_counts=True); qmod = int(vals[np.argmax(cnt)])
    minority = q != qmod; share = float(minority.mean())
    if share < 0.01: continue
    G = np.full((H, W), -1, np.int8); G[ii, jj] = (q == qmod)
    pts = []
    for (dr, dc) in ((1, 0), (0, 1)):
        A, B = G[:H - dr, :W - dc], G[dr:, dc:]
        r, c = np.nonzero((A >= 0) & (B >= 0) & (A != B))
        pts.append(np.stack([r + dr / 2, c + dc / 2], 1))
    P = np.concatenate(pts); L_vox = float(len(P) * 4)
    lat = np.zeros((2 * H, 2 * W), bool); lat[(2 * P[:, 0]).astype(int), (2 * P[:, 1]).astype(int)] = True
    lab, n = ndimage.label(ndimage.binary_dilation(lat, np.ones((3, 3))), structure=np.ones((3, 3)))
    ids = lab[(2 * P[:, 0]).astype(int), (2 * P[:, 1]).astype(int)]
    keep, specks = [], 0
    for i in range(1, n + 1):
        Q = P[ids == i]
        if len(Q) < 8: specks += 1; continue
        T = cKDTree(Q); used = np.zeros(len(Q), bool); cur = int(np.argmin(Q[:, 0] + Q[:, 1])); order = [cur]; used[cur] = True
        for _ in range(len(Q) - 1):
            d, j = T.query(Q[cur], k=min(16, len(Q)))
            nxt = next((int(x) for x in np.atleast_1d(j) if not used[x]), None)
            if nxt is None: nxt = int(np.nonzero(~used)[0][np.argmin(((Q[~used] - Q[cur]) ** 2).sum(1))])
            used[nxt] = True; order.append(nxt); cur = nxt
        keep.append(Q[order])
    cs = [None] * (len(keep) + specks)
    by_q = {int(v): round(float((q == v).sum() * 16 * VOX_CM2), 2) for v in np.unique(q) if v != qmod and (q == v).mean() >= 0.001}
    out["pages"].append({"page": k, "modal_q": qmod, "minority_share": round(share, 4),
                         "minority_area_cm2": round(float(minority.sum() * 16 * VOX_CM2), 2), "minority_area_by_q_cm2": by_q,
                         "boundary_length_vox": round(L_vox, 1), "boundary_length_mm": round(L_vox * 7.91e-3, 1),
                         "n_polylines": len(keep), "n_specks_dropped": len(cs) - len(keep),
                         "polylines_rowcol": [np.round(c, 1).tolist() for c in sorted(keep, key=len, reverse=True)]})
    p = out["pages"][-1]; print({x: p[x] for x in p if x != "polylines_rowcol"}, flush=True)
json.dump(out, open(outp, "w"))
