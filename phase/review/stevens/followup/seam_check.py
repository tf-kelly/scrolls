"""COORD 02:45 seam check (S1, S2). Read-only on the VP_DUMP of quilt2 (quilt2_vpdump.py, handedness s = 1).

quilt2: theta = atan2 about the umbilicus in [0, 2 pi), so the angular seam is theta = 0 for both the index lookup
(theta cells 0..nth-1 per winding) and the page. Theta = the page's own unwrapped angle, Theta = theta (mod 2 pi).
Sheet key q = w - floor(Theta / 2 pi).

S1  Seam location. (a) Index seam, measured: the theta of grid edges where the raw index winding w changes (a correct
    single sheet steps w by 1 at the index seam). (b) Each D1 boundary (15x15 smoothed q == modal map, as d1_main.py):
    share of boundary points with theta within +-5 deg of the seam; the same for each of the two longest polylines
    (the D4' pieces). A boundary "lies on the seam" if that share >= 0.80.
S2  Per page, share of matched vertices on the modal key for: raw integer w (no seam handling); quilt v2's q; and the
    continuous coordinate c = w + theta / 2 pi referred to the page's unwrapped angle, round(c - Theta / 2 pi).
    The last equals q identically (Theta - theta = 2 pi floor(Theta / 2 pi)); the max difference is reported.
Also for every page: seam crossings in the grid (edges where theta wraps) and the share of those edges where q steps.
  seam_check.py DUMP_DIR PAGES_DIR UMBILICUS_JSON D1_MAIN_JSON OUT.json
"""
import json, sys
import numpy as np, tifffile
from scipy import ndimage
TWO_PI = 2 * np.pi; TOL = np.deg2rad(5.0)
dump, pages, umb, d1p, outp = sys.argv[1:6]
u = json.load(open(umb)); pts = u['control_points'] if isinstance(u, dict) else u
cp = np.array([[p['z'], p['y'], p['x']] for p in pts], float); cp = cp[np.argsort(cp[:, 0])]
d1 = {p['page']: p for p in json.load(open(d1p))['pages']}


def seamdist(t):  # angular distance to theta = 0
    t = np.mod(t, TWO_PI); return np.minimum(t, TWO_PI - t)


def modal_share(v):
    _, c = np.unique(v, return_counts=True); return float(c.max() / c.sum())


out = {"seam_theta_deg": 0.0, "tolerance_deg": 5.0, "pages": []}
for k in range(10):
    z = np.load(f"{dump}/patch_{k}_q.npz"); ii, jj, wv, q, m, Th = z['ii'], z['jj'], z['wv'], z['q'], z['matched'], z['Theta']
    X, Y, Z = (tifffile.imread(f"{pages}/patch_{k}/{c}.tif").astype(float) for c in "xyz")
    H, W = X.shape
    ax, ay = np.interp(Z[ii, jj], cp[:, 0], cp[:, 2]), np.interp(Z[ii, jj], cp[:, 0], cp[:, 1])
    th = np.mod(np.arctan2(Y[ii, jj] - ay, X[ii, jj] - ax), TWO_PI)
    G = lambda a, fill: (lambda g: (g.__setitem__((ii, jj), a), g)[1])(np.full((H, W), fill, a.dtype))
    Tg, Wg, Qg = G(th, np.nan), G(wv.astype(np.int64), -99999), G(q.astype(np.int64), -99999)
    Mg = G(m.astype(np.int8), 0).astype(bool)
    c = wv + th / TWO_PI; qc = np.round(c - Th / TWO_PI).astype(np.int64)
    rec = {"page": k, "vertices_matched": int(m.sum()),
           "S2_modal_share_raw_w": round(modal_share(wv[m]), 4), "S2_modal_share_quilt2_q": round(modal_share(q[m]), 4),
           "S2_modal_share_continuous": round(modal_share(qc[m]), 4),
           "S2_max_abs_continuous_minus_q": int(np.abs(qc[m] - q[m]).max()),
           "turns": round(float(np.ptp(Th) / TWO_PI), 2)}
    # edges between 4-neighbours, both matched
    wedge_th, qedge_th, seam_edges, seam_q_steps = [], [], 0, 0
    for dr, dc in ((1, 0), (0, 1)):
        A = (slice(0, H - dr), slice(0, W - dc)); B = (slice(dr, H), slice(dc, W))
        ok = Mg[A] & Mg[B]
        ta, tb = Tg[A], Tg[B]
        wrap = ok & (np.abs(ta - tb) > np.pi)                   # theta crosses the seam on this edge
        tmid = np.where(wrap, 0.0, (ta + tb) / 2)
        wch = ok & (Wg[A] != Wg[B]); qch = ok & (Qg[A] != Qg[B])
        wedge_th.append(tmid[wch]); qedge_th.append(tmid[qch])
        seam_edges += int(wrap.sum()); seam_q_steps += int((wrap & qch).sum())
    wt, qt = np.concatenate(wedge_th), np.concatenate(qedge_th)
    rec["S1a_raw_w_change_edges"] = int(len(wt))
    rec["S1a_share_raw_w_changes_within_5deg_of_seam"] = round(float((seamdist(wt) <= TOL).mean()), 4) if len(wt) else None
    rec["seam_crossing_edges"] = seam_edges
    rec["seam_crossing_edges_where_q_steps"] = seam_q_steps
    rec["raw_q_change_edges"] = int(len(qt))
    rec["share_raw_q_changes_within_5deg_of_seam"] = round(float((seamdist(qt) <= TOL).mean()), 4) if len(qt) else None
    if k in d1:
        # D1 smoothed boundary, recomputed exactly as d1_main.py, then theta at each boundary point
        p = d1[k]; qmod = p['modal_q']
        V = np.zeros((H, W)); V[ii, jj] = 1; I = np.zeros((H, W)); I[ii, jj] = (q == qmod)
        fr = ndimage.uniform_filter(I, 15) / np.maximum(ndimage.uniform_filter(V, 15), 1e-9)
        S = np.full((H, W), -1, np.int8); S[ii, jj] = (fr[ii, jj] > 0.5)
        P = []
        for dr, dc in ((1, 0), (0, 1)):
            a_, b_ = S[:H - dr, :W - dc], S[dr:, dc:]; r, cc = np.nonzero((a_ >= 0) & (b_ >= 0) & (a_ != b_))
            P.append(np.stack([r + dr / 2, cc + dc / 2], 1))
        P = np.concatenate(P)

        def theta_at(rc):
            r0 = np.clip(np.floor(rc[:, 0]).astype(int), 0, H - 1); c0 = np.clip(np.floor(rc[:, 1]).astype(int), 0, W - 1)
            t = Tg[r0, c0]; bad = ~np.isfinite(t)
            r1 = np.clip(np.ceil(rc[:, 0]).astype(int), 0, H - 1); c1 = np.clip(np.ceil(rc[:, 1]).astype(int), 0, W - 1)
            t[bad] = Tg[r1[bad], c1[bad]]
            return t[np.isfinite(t)]
        tb = theta_at(P)
        sh = float((seamdist(tb) <= TOL).mean())
        rec["S1b_boundary_points"] = int(len(tb))
        rec["S1b_share_boundary_within_5deg_of_seam"] = round(sh, 4)
        rec["S1b_boundary_theta_deg_pct_5_50_95"] = [round(float(x), 1) for x in np.percentile(np.rad2deg(tb), [5, 50, 95])]
        rec["S1b_on_seam_ge_80pct"] = "y" if sh >= 0.8 else "n"
        pl = []
        for n, Q in enumerate(p['polylines_rowcol'][:2]):
            t = theta_at(np.array(Q)); s_ = float((seamdist(t) <= TOL).mean())
            pl.append({"piece": n + 1, "points": int(len(t)), "share_within_5deg": round(s_, 4),
                       "theta_deg_min_median_max": [round(float(x), 1) for x in (np.rad2deg(t).min(), np.median(np.rad2deg(t)), np.rad2deg(t).max())],
                       "on_seam_ge_80pct": "y" if s_ >= 0.8 else "n"})
        rec["S1b_d4_pieces"] = pl
    out["pages"].append(rec); print(json.dumps(rec), flush=True)
json.dump(out, open(outp, "w"), indent=1)
