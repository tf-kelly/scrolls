#!/usr/bin/env python3
"""S1b (1): reference-free mesh self-consistency check.

Samples point pairs 100-400 um apart ALONG the surface (via the mesh's own row/column
arc length -- not 3-D straight-line distance), snaps each point to the nearest phase-zero
along the field normal (as switchwitness/core.py's witness() does), and counts signed
sheet crossings between the snapped points with phase/x2/common.py's Field.count() --
that file is frozen and imported unmodified. A correct mesh gives count 0 for every
pair. Flags:
  (a) DBSCAN clusters of pairs with nonzero, in-support count (candidate layer jumps);
  (b) pairs close in 3-D but far apart in the mesh's own (u,v) arc-length chart
      (candidate fold-backs).
Field tuning (period) is a caller-supplied fixed value -- this module never estimates
it. See phase/notes/S1b.md for the committed period values and cluster/fold-back
thresholds, committed before this module is run against real data.
"""
import sys
from pathlib import Path
import numpy as np
import tifffile
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "phase/x2"), str(REPO / "phase/x3/switchwitness")]
import common          # phase/x2/common.py, frozen
from core import to_slab  # phase/x3/switchwitness/core.py, frozen

UM0_DEFAULT = 7.91


def load_grid(mesh_dir):
    g = np.stack([tifffile.imread(Path(mesh_dir) / f"{c}.tif").astype(np.float32) for c in "xyz"], -1)
    ok = np.isfinite(g).all(-1) & (g[..., 0] > 0) & (g[..., 2] > 0)
    g = g.copy(); g[~ok] = np.nan
    return g, ok


def arclen_u(g, um0):
    """Cumulative arc length (um) along axis=1 (within a row)."""
    step = np.linalg.norm(np.diff(g, axis=1), axis=-1)
    fill = np.nanmedian(step)
    step = np.where(np.isfinite(step), step, fill)
    return np.concatenate([np.zeros((g.shape[0], 1)), np.cumsum(step, axis=1)], axis=1) * um0


def arclen_v(g, um0):
    """Cumulative arc length (um) along axis=0 (within a column)."""
    step = np.linalg.norm(np.diff(g, axis=0), axis=-1)
    fill = np.nanmedian(step)
    step = np.where(np.isfinite(step), step, fill)
    return np.concatenate([np.zeros((1, g.shape[1])), np.cumsum(step, axis=0)], axis=0) * um0


def bind_field(fdir, fmeta):
    """Point phase/x2/common.py's module-level F/slab at fdir (mirrors core.py's
    bind_field, which is not imported directly since it also returns a
    period-derived value we compute ourselves from the committed period)."""
    common.F = Path(fdir)
    lv, org = fmeta["level"], np.array(fmeta["origin"])
    common.slab = lambda xyz: to_slab(xyz, lv, org)
    return common.Field(raw=False)


def sample_pairs(g, ok, Su, Sv, rows_mask, sep_lo, sep_hi, n, rng):
    """n pairs, each (p0, p1) both valid mesh vertices, separated by Uniform(sep_lo,
    sep_hi) um along one of the two grid parametric directions (chosen 50/50)."""
    H, W = g.shape[:2]
    pa, pb, mid, direction = [], [], [], []
    tries = 0
    max_tries = n * 40
    while len(pa) < n and tries < max_tries:
        tries += 1
        use_u = rng.random() < 0.5
        ds = rng.uniform(sep_lo, sep_hi) * rng.choice([-1.0, 1.0])
        if use_u:
            r = rng.integers(0, H)
            if not rows_mask[r]:
                continue
            c0 = rng.integers(0, W)
            if not ok[r, c0]:
                continue
            target = Su[r, c0] + ds
            c1 = int(np.searchsorted(Su[r], target))
            if c1 < 0 or c1 >= W or not ok[r, c1] or c1 == c0:
                continue
            p0, p1 = g[r, c0], g[r, c1]
        else:
            c = rng.integers(0, W)
            r0 = rng.integers(0, H)
            if not (ok[r0, c] and rows_mask[r0]):
                continue
            target = Sv[r0, c] + ds
            r1 = int(np.searchsorted(Sv[:, c], target))
            if r1 < 0 or r1 >= H or not ok[r1, c] or not rows_mask[r1] or r1 == r0:
                continue
            p0, p1 = g[r0, c], g[r1, c]
        pa.append(p0); pb.append(p1); mid.append((p0 + p1) / 2); direction.append(0 if use_u else 1)
    return (np.array(pa, np.float32), np.array(pb, np.float32),
            np.array(mid, np.float32), np.array(direction, np.int8))


def count_pairs(fld, pa, pb, snap_tmax):
    """Snap both endpoints to the nearest phase-zero along the field normal (as
    core.py's witness() does), then signed-count crossings between the snapped
    points. Returns (counts, ok) -- ok False where either endpoint failed to snap
    or the counted path left the field's support."""
    sa, _ = fld.snap(pa, tmax=snap_tmax)
    sb, _ = fld.snap(pb, tmax=snap_tmax)
    okxy = np.isfinite(sa).all(1) & np.isfinite(sb).all(1)
    counts = np.full(len(pa), np.nan)
    ok = np.zeros(len(pa), bool)
    if okxy.any():
        c_, o_ = fld.count(sa[okxy], sb[okxy])
        idx = np.where(okxy)[0]
        counts[idx] = c_
        ok[idx[o_]] = True
    return counts, ok


def cluster_flags(mid, counts, ok, eps_um, min_samples, um0):
    """mid is in L0 VOXELS (as produced by sample_pairs, straight from the mesh tif);
    DBSCAN's eps is physical (um), so mid is converted to um before clustering --
    passing mid straight through was S1b's first bug, caught by inspecting sub-
    min_samples DBSCAN labels (impossible at correct units; see S1b.md)."""
    from sklearn.cluster import DBSCAN
    flagged = ok & np.isfinite(counts) & (np.round(counts) != 0)
    pts = mid[flagged] * um0
    if len(pts) == 0:
        return [], flagged
    labels = DBSCAN(eps=eps_um, min_samples=min_samples).fit(pts).labels_
    clusters = []
    for lab in sorted(set(labels)):
        if lab == -1:
            continue
        idx = np.where(labels == lab)[0]
        clusters.append(dict(n=int(len(idx)), centroid=pts[idx].mean(0).tolist(),
                              count_median=float(np.median(counts[flagged][idx]))))
    return clusters, flagged


def foldback_candidates(g, ok, Su, Sv, rows_mask, r3d_um, along_min_um, um0, n_query, rng,
                         local_rc=None):
    """Sample n_query valid vertices; for each, KD-tree neighbours within r3d_um in
    3-D; flag a neighbour if its (Su,Sv) chart position is more than along_min_um
    away in the arc-length metric sqrt(dSu^2+dSv^2) -- i.e. close in space, far
    along the surface.

    First run (S1b) found this naive test fires on ~40% of nearby pairs on a real
    scroll cross-section: a single mesh row sweeps the WHOLE spiral at that z, so
    two points on adjacent physical wraps are legitimately close in 3-D and far
    apart in row arc length -- that is normal scroll topology, not a mesh defect.
    If local_rc=(dr,dc) is given, an extra 'local' flag additionally requires the
    neighbour's grid index to be within dr rows / dc cols -- i.e. still far apart
    along the surface despite being local in the mesh's own parametrization, which
    a legitimate cross-wrap neighbour never is. This is the one meant to catch a
    real fold-back."""
    idx = np.argwhere(ok & rows_mask[:, None])
    xyz = g[idx[:, 0], idx[:, 1]].astype(np.float64) * um0
    su = Su[idx[:, 0], idx[:, 1]]; sv = Sv[idx[:, 0], idx[:, 1]]
    tree = cKDTree(xyz)
    sel = rng.choice(len(xyz), size=min(n_query, len(xyz)), replace=False)
    out, out_local = [], []
    for i in sel:
        neigh = tree.query_ball_point(xyz[i], r3d_um)
        for j in neigh:
            if j == i:
                continue
            along = float(np.hypot(su[i] - su[j], sv[i] - sv[j]))
            if along > along_min_um:
                rec = dict(p0=xyz[i].tolist(), p1=xyz[j].tolist(),
                           r3d_um=float(np.linalg.norm(xyz[i] - xyz[j])), along_um=along)
                out.append(rec)
                if local_rc is not None:
                    dr, dc = local_rc
                    if abs(int(idx[i, 0]) - int(idx[j, 0])) <= dr and abs(int(idx[i, 1]) - int(idx[j, 1])) <= dc:
                        out_local.append(rec)
    return out, out_local
