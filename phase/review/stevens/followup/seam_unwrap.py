"""COORD 02:45 S2, done properly: theta unwrapped along the sheet itself.

quilt2 unwraps Theta from a per-row (or per-column) mean angle: Theta = base + wrap(theta - base). Where a row spans
more than pi of angle this has a branch cut inside the page: Theta jumps by 2 pi between grid neighbours, theta does
not, and q = w - floor(Theta / 2 pi) steps by 1 on a continuous sheet. Here Theta' is theta unwrapped along the page
grid: a BFS spanning tree over valid 4-neighbours (one virtual root joins all components; each disconnected island
then takes the whole-turn offset, round(median(Theta - Theta') / 2 pi), that best matches quilt2's Theta), Theta'(n) = theta(root of
its component) + sum of wrap(theta(child) - theta(parent)) along the tree path (vectorised pointer jumping). Then
q' = w - floor(Theta' / 2 pi) (s = 1, as quilt2). Check: non-tree edges with |Theta'_a - Theta'_b| > pi (a grid loop
that winds around the axis would make the unwrap path-dependent; these are counted, not hidden).

Reported per page: branch-cut edges in quilt2's Theta, residual jumps in Theta', modal share on matched vertices for
q and q', D1 raw minority area (vertices with q != modal, 16 vox^2 each, as d1_boundaries.py) for q and q', D1
smoothed minority area and regions (as d1_main.py) for q', and for the two D4' pieces per split page the share of
piece points that still lie on a q' smoothed boundary (within 2 cells).
  seam_unwrap.py DUMP_DIR PAGES_DIR UMBILICUS_JSON D1_MAIN_JSON OUT.json
"""
import json, sys
import numpy as np, tifffile
from scipy import ndimage, sparse
from scipy.sparse.csgraph import breadth_first_order, connected_components
TWO_PI = 2 * np.pi; VOX_CM2 = (7.91e-4) ** 2; CELL = 16 * VOX_CM2
dump, pages, umb, d1p, outp = sys.argv[1:6]
u = json.load(open(umb)); pts = u['control_points'] if isinstance(u, dict) else u
cp = np.array([[p['z'], p['y'], p['x']] for p in pts], float); cp = cp[np.argsort(cp[:, 0])]
d1 = {p['page']: p for p in json.load(open(d1p))['pages']}
wrap = lambda a: np.mod(a + np.pi, TWO_PI) - np.pi


def modal(v):
    vals, c = np.unique(v, return_counts=True); return int(vals[np.argmax(c)]), float(c.max() / c.sum())


def smoothed(qg_vals, qmod, ii, jj, H, W):
    V = np.zeros((H, W)); V[ii, jj] = 1; I = np.zeros((H, W)); I[ii, jj] = (qg_vals == qmod)
    fr = ndimage.uniform_filter(I, 15) / np.maximum(ndimage.uniform_filter(V, 15), 1e-9)
    S = np.full((H, W), -1, np.int8); S[ii, jj] = (fr[ii, jj] > 0.5); return S


def unwrap_tree(th, ii, jj, H, W):
    n = len(th); idx = np.full((H, W), -1, np.int64); idx[ii, jj] = np.arange(n)
    ea, eb = [], []
    for dr, dc in ((1, 0), (0, 1)):
        a, b = idx[:H - dr, :W - dc].ravel(), idx[dr:, dc:].ravel(); ok = (a >= 0) & (b >= 0); ea.append(a[ok]); eb.append(b[ok])
    ea, eb = np.concatenate(ea), np.concatenate(eb)
    A = sparse.coo_matrix((np.ones(len(ea), np.int8), (ea, eb)), shape=(n, n)).tocsr()
    ncomp, lab = connected_components(A, directed=False)
    first = np.unique(lab, return_index=True)[1]                       # one node per component
    R = n                                                              # virtual root
    va = np.concatenate([ea, np.full(len(first), R)]); vb = np.concatenate([eb, first])
    A = sparse.coo_matrix((np.ones(len(va), np.int8), (va, vb)), shape=(n + 1, n + 1)).tocsr()
    _, pred = breadth_first_order(A, R, directed=False, return_predecessors=True)
    pred = pred[:n]
    d = np.where(pred == R, th, wrap(th - th[np.where(pred == R, 0, pred)]))
    ptr = np.where(pred == R, -1, pred).astype(np.int64); acc = d.copy()
    while (ptr >= 0).any():
        m = ptr >= 0; p = ptr[m]
        acc_new = acc.copy(); acc_new[m] = acc[m] + acc[p]
        ptr_new = ptr.copy(); ptr_new[m] = ptr[p]
        acc, ptr = acc_new, ptr_new
    return acc, ncomp, lab, ea, eb


out = {"pages": []}
for k in range(10):
    z = np.load(f"{dump}/patch_{k}_q.npz"); ii, jj, wv, q, m, Th = z['ii'], z['jj'], z['wv'], z['q'], z['matched'], z['Theta']
    X, Y, Z = (tifffile.imread(f"{pages}/patch_{k}/{c}.tif").astype(float) for c in "xyz"); H, W = X.shape
    ax, ay = np.interp(Z[ii, jj], cp[:, 0], cp[:, 2]), np.interp(Z[ii, jj], cp[:, 0], cp[:, 1])
    th = np.mod(np.arctan2(Y[ii, jj] - ay, X[ii, jj] - ax), TWO_PI); del X, Y, Z
    Th2, ncomp, lab, ea, eb = unwrap_tree(th, ii, jj, H, W)
    # islands: the grid has disconnected components; each gets the whole-turn offset that best matches quilt2's Theta
    # (quilt2's row/column base is the only link across gaps). Within an island the unwrap follows the sheet.
    kc = np.round(ndimage.median(Th - Th2, lab, np.arange(ncomp)) / TWO_PI)
    Th2 = Th2 + TWO_PI * kc[lab]
    rj = np.abs(Th2[ea] - Th2[eb]) > np.pi
    resid = int(rj.sum())
    assert np.allclose(np.mod(Th2, TWO_PI), th, atol=1e-6) or np.allclose(np.mod(Th2 - th + np.pi, TWO_PI) - np.pi, 0, atol=1e-6)
    cuts = int((np.abs(Th[ea] - Th[eb]) > np.pi).sum())
    valid = wv > -9999
    q2 = np.where(valid, wv - np.floor(Th2 / TWO_PI).astype(np.int64), -99999)
    qm, sh = modal(q[m]); qm2, sh2 = modal(q2[m])
    rec = {"page": k, "grid_components": int(ncomp), "quilt2_theta_branch_cut_edges": cuts,
           "unwrapped_residual_jump_edges": resid,
           "residual_rows_cols_median": [float(np.median(ii[ea[rj]])), float(np.median(jj[ea[rj]]))] if resid else None,
           "vertices_in_largest_island_share": round(float(np.bincount(lab).max() / len(lab)), 4), "turns_quilt2": round(float(np.ptp(Th) / TWO_PI), 2),
           "turns_unwrapped": round(float(np.ptp(Th2) / TWO_PI), 2),
           "modal_share_q": round(sh, 4), "modal_share_q_unwrapped": round(sh2, 4),
           "raw_minority_cm2_q": round(float(((q != qm) & valid).sum() * CELL), 2),
           "raw_minority_cm2_q_unwrapped": round(float(((q2 != qm2) & valid).sum() * CELL), 2),
           "minority_by_key_cm2_q_unwrapped": {str(int(v)): round(float((q2 == v).sum() * CELL), 2)
                                               for v in np.unique(q2[valid]) if v != qm2 and (q2 == v).mean() >= 0.001}}
    if k in d1:
        S2 = smoothed(q2, qm2, ii, jj, H, W)
        lab, nl = ndimage.label(S2 == 0)
        areas = np.bincount(lab.ravel())[1:] * CELL
        rec["smoothed_minority_cm2_q_unwrapped"] = round(float((S2 == 0).sum() * CELL), 2)
        rec["smoothed_minority_cm2_q_d1"] = d1[k]["smoothed_minority_area_cm2"]
        rec["regions_ge_0p5cm2_q_unwrapped"] = sorted([round(float(a), 2) for a in areas if a >= 0.5], reverse=True)[:6]
        Bd = np.zeros((H, W), bool)
        for dr, dc in ((1, 0), (0, 1)):
            a_, b_ = S2[:H - dr, :W - dc], S2[dr:, dc:]; e = (a_ >= 0) & (b_ >= 0) & (a_ != b_)
            Bd[:H - dr, :W - dc] |= e; Bd[dr:, dc:] |= e
        Bd = ndimage.binary_dilation(Bd, np.ones((5, 5)))
        pcs = []
        for n_, Q in enumerate(d1[k]["polylines_rowcol"][:2]):
            Q = np.array(Q); r0 = np.clip(Q[:, 0].astype(int), 0, H - 1); c0 = np.clip(Q[:, 1].astype(int), 0, W - 1)
            pcs.append({"piece": n_ + 1, "share_still_on_boundary_q_unwrapped": round(float(Bd[r0, c0].mean()), 4),
                        "share_of_piece_near_quilt2_branch_cut": None})
        # which D4' piece points sit on a quilt2 branch cut (within 2 cells)
        Cg = np.zeros((H, W), bool)
        for dr, dc in ((1, 0), (0, 1)):
            Tg = np.full((H, W), np.nan); Tg[ii, jj] = Th
            e = np.abs(Tg[:H - dr, :W - dc] - Tg[dr:, dc:]) > np.pi; e &= np.isfinite(Tg[:H - dr, :W - dc]) & np.isfinite(Tg[dr:, dc:])
            Cg[:H - dr, :W - dc] |= e; Cg[dr:, dc:] |= e
        Cg = ndimage.binary_dilation(Cg, np.ones((5, 5)))
        for n_, Q in enumerate(d1[k]["polylines_rowcol"][:2]):
            Q = np.array(Q); r0 = np.clip(Q[:, 0].astype(int), 0, H - 1); c0 = np.clip(Q[:, 1].astype(int), 0, W - 1)
            pcs[n_]["share_of_piece_near_quilt2_branch_cut"] = round(float(Cg[r0, c0].mean()), 4)
        rec["d4_pieces"] = pcs
    out["pages"].append(rec); print(json.dumps(rec), flush=True)
json.dump(out, open(outp, "w"), indent=1)
