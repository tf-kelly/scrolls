"""Band spacing from CT, SessC's definition (phase/g2b/covariates.py, SessC-2 Amendment 2; s4_spacing_scroll4.py), pooled
over boxes drawn from a region.

Per box (256^3 raw L0 CT around a sample point, clipped to the scan):
  Gaussian sigma 1; the box's Otsu threshold; block normal = dominant eigenvector of the gradient structure tensor
  (Gaussian-derivative sigma 1) over the central 128^3; 11 x 11 lines along the normal (in-plane offsets -50..50 step
  10), samples -60..60 voxels at 0.5 steps (nearest voxel, clipped to the box); bands = runs above threshold of >= 3
  voxels not touching either line end; spacings = differences of consecutive band centres along each line.
Region: `n_boxes` sample points drawn with default_rng(seed) from the region's valid patch vertices; the estimate is
the median of all pooled spacings x 7.91 um. Only the sampling and pooling are additions to SessC's definition.
"""
from __future__ import annotations

import numpy as np

VOX_UM = 7.91
BOX = 256


def runs(mask1d):
    d = np.diff(np.r_[0, mask1d.astype(int), 0])
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def box_spacings(ct_box, centre_local):
    from scipy import ndimage as ndi
    from skimage.filters import threshold_otsu
    Sm = ndi.gaussian_filter(ct_box.astype(np.float32), 1.0)
    thr = float(threshold_otsu(Sm))
    sl = np.asarray(centre_local)
    lo = np.maximum(sl - 64, 0); hi = np.minimum(sl + 64, Sm.shape)
    blk = tuple(slice(a, b) for a, b in zip(lo, hi))
    G = np.stack([ndi.gaussian_filter(Sm, 1.0, order=o)[blk].ravel() for o in ((1, 0, 0), (0, 1, 0), (0, 0, 1))])
    w, v = np.linalg.eigh(G @ G.T / G.shape[1]); nb = v[:, 2]
    e1 = np.cross(nb, [1, 0, 0] if abs(nb[0]) < 0.9 else [0, 1, 0]); e1 /= np.linalg.norm(e1); e2 = np.cross(nb, e1)
    ss = np.arange(-60, 60.0001, 0.5); lens, spac = [], []
    hi_i = np.array(Sm.shape) - 1
    for u in np.arange(-50, 51, 10):
        for vv in np.arange(-50, 51, 10):
            P = sl + u * e1 + vv * e2 + ss[:, None] * nb
            q = np.clip(np.round(P).astype(int), 0, hi_i)
            rr = [(a, b) for a, b in runs(Sm[tuple(q.T)] > thr) if a > 0 and b < len(ss) and (b - a) * 0.5 >= 3]
            lens += [(b - a) * 0.5 for a, b in rr]
            c = [(a + b) / 4 for a, b in rr]
            spac += list(np.diff(c))
    return dict(otsu=thr, normal_zyx=nb.round(4).tolist(), bands=len(lens), spacings=spac,
                thickness_median_vox=float(np.median(lens)) if lens else None,
                spacing_median_vox=float(np.median(spac)) if spac else None)


def estimate(ct0, points_xyz, scan_shape_zyx, n_boxes=16, seed=0, log=print):
    """ct0: sources.CT at level 0. points_xyz: (N, 3) L0 x,y,z patch vertices of the region."""
    rng = np.random.default_rng(seed)
    pts = np.asarray(points_xyz, float)
    sel = pts[rng.choice(len(pts), min(n_boxes, len(pts)), replace=False)]
    shape = np.asarray(scan_shape_zyx)
    allsp, boxes = [], []
    for p in sel:
        c = np.round(p[::-1]).astype(int)                       # z, y, x
        lo = np.clip(c - BOX // 2, 0, np.maximum(shape - BOX, 0)); hi = np.minimum(lo + BOX, shape)
        arr, info = ct0.read(lo.tolist(), hi.tolist())
        r = box_spacings(arr, c - lo)
        r.update(centre_zyx=c.tolist(), missing=(info or {}).get("missing") if isinstance(info, dict) else None)
        allsp += r["spacings"]
        boxes.append({k: v for k, v in r.items() if k != "spacings"} | dict(n_spacings=len(r["spacings"])))
        log(f"[spacing] box {len(boxes)}/{len(sel)} at {c.tolist()}: median {r['spacing_median_vox']} vox, {len(r['spacings'])} spacings")
    med = float(np.median(allsp)) if allsp else float("nan")
    per_box = [b["spacing_median_vox"] for b in boxes if b["spacing_median_vox"] is not None]
    return dict(spacing_vox=med, spacing_um=med * VOX_UM, n_spacings=len(allsp), n_boxes=len(boxes),
                per_box_median_vox=per_box, per_box_iqr_vox=[float(np.percentile(per_box, 25)), float(np.percentile(per_box, 75))] if per_box else None,
                pooled_iqr_vox=[float(np.percentile(allsp, 25)), float(np.percentile(allsp, 75))] if allsp else None,
                definition="SessC-2 Amendment 2 (phase/g2b/covariates.py) per box; boxes sampled from region vertices, default_rng(%d); pooled median" % seed,
                boxes=boxes)
