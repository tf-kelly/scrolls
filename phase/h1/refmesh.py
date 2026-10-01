"""H1: reference-mesh lookup, reusable at arbitrary world (x,y,z) points.

Re-derives phase/x7/x7_v9.py step 1 (theta0-cut, sign-oriented, turn-counted unwrap of the
complete_surface_200um.npz reference mesh) as an importable, queryable object, WITHOUT touching or
re-executing v9's frozen file. v9 only exposed this reference at x6b patch centroids
(X7_v9_patch_k.csv); H1 needs it at winding-sync's own seed coordinates too.

Per protocol/COMMON.md and CLAUDE.md: this mesh is a reference, not ground truth. Nothing here
elevates it to "truth" -- it is the SAME reference X7/X6/X9 already use, applied identically to
every arm scored in H1.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.spatial import cKDTree

R = Path(__file__).resolve().parents[2]
X6 = R / "phase/x6"
X1 = R / "phase/x1"
DS = R / "phase/data_small/x4test/complete_surface_200um.npz"
VOX_UM = 7.91
TH0 = 0.0


def build_axis(nodes, pos):
    """Same axis-of-scroll estimate v9 uses: patch centroids of the x6b node set, area-weighted,
    block-averaged in 256-vox z bins, smoothed. Returns axis_xy(z) -> (x, y)."""
    patches = {int(r["id"]): r for r in csv.DictReader(open(X1 / "patches.csv"))}
    pid = [int(p) for p in nodes]
    c = np.array([[float(patches[p]["cx"]), float(patches[p]["cy"]), float(patches[p]["cz"])] for p in pid])
    n_pts = np.array([float(patches[p]["n"]) for p in pid])
    zb = np.arange(np.floor(c[:, 2].min() / 256) * 256, c[:, 2].max() + 256, 256)
    ax_x = np.full(len(zb) - 1, np.nan)
    ax_y = np.full(len(zb) - 1, np.nan)
    for i in range(len(zb) - 1):
        m = (c[:, 2] >= zb[i]) & (c[:, 2] < zb[i + 1])
        if m.any():
            ax_x[i] = np.average(c[m, 0], weights=n_pts[m])
            ax_y[i] = np.average(c[m, 1], weights=n_pts[m])
    ok = np.isfinite(ax_x)
    zc = (zb[:-1] + zb[1:]) / 2
    ax_x = uniform_filter1d(np.interp(zc, zc[ok], ax_x[ok]), 3, mode="nearest")
    ax_y = uniform_filter1d(np.interp(zc, zc[ok], ax_y[ok]), 3, mode="nearest")

    def axis_xy(z):
        return np.interp(z, zc, ax_x), np.interp(z, zc, ax_y)

    return axis_xy, patches


def ang(p, axis_xy):
    ax_, ay_ = axis_xy(p[..., 2])
    return np.mod(np.arctan2(p[..., 1] - ay_, p[..., 0] - ax_) - TH0, 2 * np.pi)


def cross(t1, t2):
    e = t1 + (np.mod(t2 - t1 + np.pi, 2 * np.pi) - np.pi)
    return np.where(e >= 2 * np.pi, 1, np.where(e < 0, -1, 0))


class RefMesh:
    """Queryable theta0-cut turn-counted reference. `.k_ref(xyz)` -> (k, ok) per point."""

    def __init__(self, axis_xy, zlo, zhi):
        G = np.load(DS)["xyz_half_vox"]
        valid = (G != 65535).all(-1)
        G = G.astype(np.float64) / 2
        rows = [v for v in range(G.shape[0]) if valid[v].any() and zlo <= np.median(G[v, valid[v], 2]) <= zhi]
        TH = {}
        n_gap_pred = 0
        for v in rows:
            cols = np.where(valid[v])[0]
            q = G[v, cols]
            ax_, ay_ = axis_xy(q[:, 2])
            t = np.arctan2(q[:, 1] - ay_, q[:, 0] - ax_)
            r_mm = np.hypot(q[:, 0] - ax_, q[:, 1] - ay_) * VOX_UM / 1000
            d = np.mod(np.diff(t) + np.pi, 2 * np.pi) - np.pi
            gap = np.diff(cols)
            dirn = np.sign(np.median(d[gap == 1])) if (gap == 1).any() else 1.0
            big = gap > 1
            pred = dirn * gap * 0.2 / np.maximum((r_mm[:-1] + r_mm[1:]) / 2, 0.05)
            d[big] += 2 * np.pi * np.round((pred[big] - d[big]) / (2 * np.pi))
            n_gap_pred += int(big.sum())
            TH[v] = (cols, np.r_[t[0], t[0] + np.cumsum(d)], r_mm)
        order_rows = sorted(rows, key=lambda v: -len(TH[v][0]))
        root = order_rows[0]
        done_rows = {root}
        shifts = []
        for v in sorted(rows, key=lambda v: abs(v - root)):
            if v in done_rows:
                continue
            nb = min(done_rows, key=lambda u: abs(u - v))
            cv, tv, _ = TH[v]
            cu, tu, _ = TH[nb]
            com, iv, iu = np.intersect1d(cv, cu, return_indices=True)
            if len(com) < 5:
                done_rows.add(v)
                continue
            n = np.round(np.median(tv[iv] - tu[iu]) / (2 * np.pi))
            TH[v] = (cv, tv - 2 * np.pi * n, TH[v][2])
            shifts.append(int(n))
            done_rows.add(v)
        dTdr = [np.sum(np.diff(TH[v][1]) * np.diff(TH[v][2])) for v in rows]
        S_REF = int(np.sign(np.sum(dTdr)))
        VX = np.concatenate([G[v, TH[v][0]] for v in rows])
        VT = np.concatenate([S_REF * (TH[v][1] - TH0) / (2 * np.pi) for v in rows])
        self.tree = cKDTree(VX)
        self.VT = VT
        self.S_REF = S_REF
        self.axis_xy = axis_xy
        self.stats = dict(reference_rows=len(rows), vertices=int(len(VX)), s_ref=S_REF,
                           gap_branch_predictions=n_gap_pred, rows_unaligned=len(rows) - len(shifts) - 1)

    def k_ref(self, xyz, max_dist_vox=30.0):
        """xyz: (N,3) world L0 voxel coords. Returns (k floor'd to int turn, ok mask)."""
        d, i = self.tree.query(xyz)
        ok = d < max_dist_vox
        k = np.full(len(xyz), np.nan)
        k[ok] = np.floor(self.VT[i[ok]])
        return k, ok

    def theta(self, xyz):
        return ang(xyz, self.axis_xy)

    def cross_theta0(self, p1, p2):
        return cross(self.theta(p1), self.theta(p2))
