#!/usr/bin/env python3
"""P1FIX step 1 (P1FIX_PROTOCOL.md): a page's index key, seam-free, from SessA's own vertex matching.

Page vertices: every STEP-th node of the page's tifxyz grid (4-vox grid, STEP 4 -> 16 vox). Index patches: tifxyz
patches of the Scroll 4 zips whose bbox is within 64 vox of the page's; their full-resolution points are streamed and
only those within 20 vox of a page vertex are kept. A page vertex takes the patch of the nearest kept point within
4 vox; its key = round(k + s * (thN_patch - Theta') / 2 pi) with Theta' the page angle about the index axis unwrapped
along the page grid (BFS spanning tree over valid 4-neighbours, largest connected island only).
Smoothing: SessD's rule scaled to this grid (majority of (key == modal) in a window of 60 vox: 4 x 4 nodes at 16 vox).
Outputs (OUT_DIR): key.npz (grid ii, jj, xyz, patch, key, theta_unwrapped, smoothed-on-modal), summary.json.
Usage: p1fix_page_key.py PAGES_ZIP PAGE WRAP_INDEX_CSV AXIS_FILE OUT_DIR ZIP [ZIP ...] [--step 4] [--s 1]"""
import io, json, re, sys, time, zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile
from scipy import ndimage, sparse
from scipy.sparse.csgraph import breadth_first_order, connected_components
from scipy.spatial import cKDTree

TWO_PI = 2 * np.pi; VOX_CM2 = (7.91e-4) ** 2
T0 = time.time(); log = lambda *m: print(f"[{time.time() - T0:7.1f}s]", *m, flush=True)


def grid(z, pre):
    g = [tifffile.imread(io.BytesIO(z.read(pre + c + ".tif"))).astype(np.float64) for c in "xyz"]
    v = (g[0] > 0) & np.isfinite(g[0]) & np.isfinite(g[1]) & np.isfinite(g[2])
    return g, v


def main():
    a = sys.argv[1:]; opt = lambda k, d: type(d)(a[a.index(k) + 1]) if k in a else d
    step, s = opt("--step", 4), opt("--s", 1)
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or not a[i - 1].startswith("--"))]
    pages_zip, page, wi_csv, axf, out = pos[0], int(pos[1]), pos[2], pos[3], Path(pos[4]); zips = pos[5:]; out.mkdir(parents=True, exist_ok=True)
    A = np.loadtxt(axf, delimiter=",", ndmin=2); ax = lambda zz: (np.interp(zz, A[:, 0], A[:, 2]), np.interp(zz, A[:, 0], A[:, 1]))
    wi = pd.read_csv(wi_csv).set_index("patch")
    zp = zipfile.ZipFile(pages_zip); meta = json.loads(zp.read(f"patch_{page}/meta.json"))
    (gx, gy, gz), v = grid(zp, f"patch_{page}/")
    gx, gy, gz, v = gx[::step, ::step], gy[::step, ::step], gz[::step, ::step], v[::step, ::step]; H, W = v.shape
    # largest 4-connected island
    lab, n = ndimage.label(v); sizes = ndimage.sum(v, lab, range(1, n + 1)); big = 1 + int(np.argmax(sizes))
    keep = lab == big; ii, jj = np.nonzero(keep); P = np.c_[gx[ii, jj], gy[ii, jj], gz[ii, jj]]
    log("page", page, "grid", v.shape, "valid", int(v.sum()), "islands", n, "largest", int(keep.sum()))
    # unwrap theta along the grid
    axx, axy = ax(P[:, 2]); th = np.mod(np.arctan2(P[:, 1] - axy, P[:, 0] - axx), TWO_PI)
    idx = -np.ones((H, W), np.int64); idx[ii, jj] = np.arange(len(ii))
    e = []
    for di, dj in ((0, 1), (1, 0)):
        a0 = idx[:H - di, :W - dj]; b0 = idx[di:, dj:]; m = (a0 >= 0) & (b0 >= 0); e.append(np.c_[a0[m], b0[m]])
    e = np.vstack(e); G = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(ii),) * 2).tocsr(); G = G + G.T
    order, pred = breadth_first_order(G, 0, directed=False, return_predecessors=True)
    Th = np.zeros(len(ii)); Th[0] = th[0]
    wrap = lambda x: np.mod(x + np.pi, TWO_PI) - np.pi
    for u in order[1:]: Th[u] = Th[pred[u]] + wrap(th[u] - th[pred[u]])
    resid = int((np.abs(Th[e[:, 0]] - Th[e[:, 1]]) > np.pi).sum())
    log("unwrap done; residual non-tree jumps", resid)
    # stream index patches near the page
    lo, hi = np.array(meta["bbox"][0]) - 64, np.array(meta["bbox"][1]) + 64
    tree_p = cKDTree(P); kept_pts, kept_id = [], []; nread = 0
    for zn in zips:
        z = zipfile.ZipFile(zn)
        for nm in z.namelist():
            mm = re.search(r"patch_(\d+)/meta.json$", nm)
            if not mm: continue
            pid = int(mm.group(1))
            if pid not in wi.index: continue
            b = np.array(json.loads(z.read(nm))["bbox"], float)
            if not (np.all(b[1] >= lo) and np.all(b[0] <= hi)): continue
            (qx, qy, qz), qv = grid(z, nm[:-9]); Q = np.c_[qx[qv], qy[qv], qz[qv]]; nread += 1
            if not len(Q): continue
            d, _ = tree_p.query(Q, k=1, distance_upper_bound=20)
            m = np.isfinite(d)
            if m.any(): kept_pts.append(Q[m]); kept_id.append(np.full(int(m.sum()), pid))
    Qa = np.vstack(kept_pts); Qid = np.concatenate(kept_id); log("patches read", nread, "kept points", len(Qa), "patches kept", len(np.unique(Qid)))
    d, j = cKDTree(Qa).query(P, k=1, distance_upper_bound=4)
    ok = np.isfinite(d); pid = np.where(ok, Qid[np.minimum(j, len(Qid) - 1)], -1)
    k = wi.k_q3c.reindex(pid[ok]).values; thN = wi.thN.reindex(pid[ok]).values
    key = np.full(len(P), np.iinfo(np.int64).min, np.int64); key[ok] = np.rint(k + s * (thN - Th[ok]) / TWO_PI).astype(np.int64)
    vals, cnt = np.unique(key[ok], return_counts=True); modal = int(vals[np.argmax(cnt)])
    # smoothing (SessD's rule, 60-vox window)
    V = np.zeros((H, W)); V[ii[ok], jj[ok]] = 1; I = np.zeros((H, W)); I[ii[ok], jj[ok]] = key[ok] == modal
    win = max(1, int(round(60 / (4 * step))))
    fr = ndimage.uniform_filter(I, win) / np.maximum(ndimage.uniform_filter(V, win), 1e-9); onm = fr[ii, jj] > 0.5
    cell = (4 * step) ** 2 * VOX_CM2
    summ = dict(page=page, step=step, s=s, grid=[H, W], valid=int(v.sum()), islands=int(n), largest_island=int(keep.sum()),
                excluded_island_area_cm2=round(float((v.sum() - keep.sum()) * cell), 2), residual_unwrap_jumps=resid,
                matched=int(ok.sum()), matched_share=round(float(ok.mean()), 4), modal_key=modal,
                modal_share_matched=round(float((key[ok] == modal).mean()), 4),
                key_counts={int(a_): int(b_) for a_, b_ in zip(vals, cnt)},
                minority_area_raw_cm2=round(float((key[ok] != modal).sum() * cell), 2),
                minority_area_smoothed_cm2=round(float(((~onm) & ok).sum() * cell), 2),
                patches_matched=int(len(np.unique(pid[ok]))), smoothing_window_nodes=win)
    np.savez_compressed(out / f"page{page}_key.npz", ii=ii, jj=jj, xyz=P, patch=pid, key=key, theta_unwrapped=Th, on_modal=onm, matched=ok)
    json.dump(summ, open(out / f"page{page}_summary.json", "w"), indent=1); print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
