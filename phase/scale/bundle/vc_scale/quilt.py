"""QUILT: one surface per winding from the traced patches, with the fitted surface filling the gaps.

  python -m vc_scale.quilt build --dataset DS --wrap-index wrap_index.csv --flags unsatisfied.csv \
         --fit-source FLATTEN_OUT/source/spiral-checkpoint.tifxyz --out OUT [--cell 4] [--pitch-um 134]

Per winding w of the checker's index (one LP component; per-vertex winding w = k_patch + s * cross(theta_patch,
theta_vertex), theta = atan2(y - ay(z), x - ax(z)) mod 2 pi, the checker's own cut convention):
  1. flagged patches (any row of the checker's unsatisfied.csv) are dropped;
  2. patch vertices -> (theta, z, r) about the axis; each patch's mean r per cell of `cell` voxels
     (arc length at the winding's median radius x z);
  3. a cell where >= 2 patches disagree by more than `conflict_frac` x pitch is CONFLICT and left empty; else the
     cell's r is the mean of its patches' means (TRACE);
  4. empty cells are FILLED from the fitted surface: the fitted sheet (villa winding) nearest the traces, carried
     from the nearest trace cell, plus a membrane correction: the trace-minus-fit residual, harmonic (Laplace)
     between the trace cells and zero at `decay_cells` cells from any trace, so trace/fit seams do not step.
The same conflict detector is also run on ALL patches (flagged included) to compare its conflicting pairs with the
checker's flagged joins (precision/recall both ways).

Writes OUT/windings/w<w>/{x,y,z,label}.tif + meta.json (label 1 trace, 2 fill, 3 conflict, 0 none), OUT/concat.tifxyz
(all windings side by side, theta increasing, subsampled to `concat_step` voxels, for the lasagna flatten),
OUT/labels_pts.npy (points + label for the render's support map), OUT/quilt.json and OUT/quilt_table.md.
"""
import argparse
import csv
import json
import os
import time
from collections import defaultdict

import numpy as np
import tifffile
from scipy import ndimage

VOX_UM = 7.91
LAB_NONE, LAB_TRACE, LAB_FILL, LAB_CONFLICT = 0, 1, 2, 3


def _log(*a):
    print(f'[{time.strftime("%H:%M:%S")}]', *a, flush=True)


def cross(t1, t2):
    e = t1 + (np.mod(t2 - t1 + np.pi, 2 * np.pi) - np.pi)
    return np.where(e >= 2 * np.pi, 1, np.where(e < 0, -1, 0))


def load_axis(path):
    u = json.load(open(path))
    pts = u['control_points'] if isinstance(u, dict) else u
    cp = np.array([[p['z'], p['y'], p['x']] for p in pts], np.float64)
    cp = cp[np.argsort(cp[:, 0])]
    return lambda z: (np.interp(z, cp[:, 0], cp[:, 2]), np.interp(z, cp[:, 0], cp[:, 1]))   # (ax, ay)


def read_tifxyz(d):
    x = tifffile.imread(os.path.join(d, 'x.tif')).astype(np.float64)
    y = tifffile.imread(os.path.join(d, 'y.tif')).astype(np.float64)
    z = tifffile.imread(os.path.join(d, 'z.tif')).astype(np.float64)
    v = (x != -1) & (y != -1) & (z != -1)
    return x, y, z, v


# ------------------------------------------------------------------------------------------------ patches
def _upsample(x, y, z, v, f=2):
    """Bilinear x f upsampling of a tifxyz grid inside valid quads only (vertex spacing 4 -> 2 voxels), so that
    rasterising on `cell`-voxel cells does not alias (every covered cell receives points)."""
    q = v[:-1, :-1] & v[1:, :-1] & v[:-1, 1:] & v[1:, 1:]
    ii, jj = np.nonzero(q)
    t = (np.arange(f) / f)
    out = []
    for arr in (x, y, z):
        a00, a01, a10, a11 = arr[ii, jj], arr[ii, jj + 1], arr[ii + 1, jj], arr[ii + 1, jj + 1]
        vals = []
        for u in t:
            for w in t:
                vals.append((1 - u) * (1 - w) * a00 + (1 - u) * w * a01 + u * (1 - w) * a10 + u * w * a11)
        out.append(np.concatenate(vals))
    return out[0], out[1], out[2]


def collect_points(ds, K, flagged, axis, s, component, cell, upsample=2):
    """Two passes over the patches. Pass 1: each winding's median radius (fixes its theta resolution). Pass 2: each
    patch's points (upsampled) -> per (winding, cell) mean r of that patch. Returns dict w -> dict(ith, iz, pid, r,
    flag) of (cell, patch) aggregates, per-winding (nth, R), and z0/nz of the common z grid."""
    pdir = os.path.join(ds, 'verified_patches')
    ids = sorted(os.listdir(pdir), key=lambda p: (len(p), p))
    ids = [p for p in ids if p in K and K[p][2] == component]
    rad = defaultdict(list)
    zmin, zmax = np.inf, -np.inf

    def load(pid):
        x, y, z, v = read_tifxyz(os.path.join(pdir, pid))
        if not v.any():
            return None
        X, Y, Z = _upsample(x, y, z, v, upsample)
        if not len(X):
            return None
        ax, ay = axis(Z)
        th = np.mod(np.arctan2(Y - ay, X - ax), 2 * np.pi)
        r = np.hypot(X - ax, Y - ay)
        k, thN, _ = K[pid]
        w = k + s * cross(np.full(th.shape, thN), th)
        return th, Z, r, w

    for n, pid in enumerate(ids):
        L = load(pid)
        if L is None:
            continue
        th, Z, r, w = L
        zmin, zmax = min(zmin, float(Z.min())), max(zmax, float(Z.max()))
        for wv in np.unique(w):
            m = w == wv
            rad[int(wv)].append((float(np.median(r[m])), int(m.sum())))
        if n % 10000 == 0:
            _log(f'pass 1: {n}/{len(ids)} patches')
    geom = {}
    for w, l in rad.items():
        rr = np.array([a for a, _ in l]); ww = np.array([b for _, b in l], float)
        o = np.argsort(rr); cw = np.cumsum(ww[o])
        Rw = float(rr[o][np.searchsorted(cw, cw[-1] / 2)])
        geom[w] = (max(8, int(np.ceil(2 * np.pi * Rw / cell))), Rw)
    acc = defaultdict(lambda: defaultdict(list))
    pidx = {}
    for n, pid in enumerate(ids):
        L = load(pid)
        if L is None:
            continue
        th, Z, r, w = L
        i = pidx.setdefault(pid, len(pidx))
        f = pid in flagged
        for wv in np.unique(w):
            m = w == wv
            nth = geom[int(wv)][0]
            ith = np.clip((th[m] / (2 * np.pi) * nth).astype(np.int64), 0, nth - 1)
            izr = Z[m] / cell
            key = np.floor(izr).astype(np.int64) * nth + ith
            ks, inv = np.unique(key, return_inverse=True)
            mr = np.bincount(inv, weights=r[m]) / np.bincount(inv)
            a = acc[int(wv)]
            a['key'].append(ks); a['r'].append(mr.astype(np.float32))
            a['pid'].append(np.full(len(ks), i, np.int32)); a['flag'].append(np.full(len(ks), f, bool))
        if n % 10000 == 0:
            _log(f'pass 2: {n}/{len(ids)} patches')
    out = {w: {k2: np.concatenate(v2) for k2, v2 in a.items()} for w, a in acc.items()}
    return out, {i: p for p, i in pidx.items()}, geom, (zmin, zmax)


def cell_stats(ith, iz, pid, r, nth, thr):
    """Vectorised per-cell statistics. Per (cell, patch): mean r of the patch's vertices in the cell. Per cell:
    n patches, mean of the patch means, conflict = n >= 2 and (max - min) > thr, and the extreme (min, max) patch
    pair of each conflict cell. Also returns the (cell, patch) groups for co-location tests."""
    cell = iz.astype(np.int64) * nth + ith
    key = cell * (1 << 31) + pid.astype(np.int64)
    ks, inv = np.unique(key, return_inverse=True)
    cnt = np.bincount(inv)
    pm = (np.bincount(inv, weights=r.astype(np.float64)) / cnt).astype(np.float32)   # per (cell, patch) mean r
    gc = ks >> 31
    gp = (ks & ((1 << 31) - 1)).astype(np.int64)
    cs, cst = np.unique(gc, return_index=True)
    n = np.diff(np.append(cst, len(gc))).astype(np.int32)
    rmax = np.maximum.reduceat(pm, cst)
    rmin = np.minimum.reduceat(pm, cst)
    rmean = (np.add.reduceat(pm.astype(np.float64), cst) / n).astype(np.float32)
    conflict = (n >= 2) & ((rmax - rmin) > thr)
    # extreme pair per conflict cell: sort groups by (cell, pm)
    o = np.lexsort((pm, gc))
    first = o[cst]                       # min-r patch of each cell (groups of a cell are contiguous in gc order)
    last = o[np.append(cst[1:], len(gc)) - 1]
    lo, hi = gp[first][conflict], gp[last][conflict]
    pairs = np.stack([np.minimum(lo, hi), np.maximum(lo, hi)], 1) if len(lo) else np.zeros((0, 2), np.int64)
    return cs, n, rmean, conflict, pairs, (gc, gp, rmin, rmax)


def colocated(groups, pa, pb):
    """For patch index pairs (pa, pb): do they share at least one cell? groups = (cell, patch) arrays."""
    gc, gp = groups[0], groups[1]
    o = np.argsort(gp, kind='stable')
    gps, st = np.unique(gp[o], return_index=True)
    en = np.append(st[1:], len(o))
    where = {int(p): (s_, e_) for p, s_, e_ in zip(gps, st, en)}
    out = np.zeros(len(pa), bool)
    for i, (p, q) in enumerate(zip(pa, pb)):
        if p in where and q in where:
            a_ = gc[o[where[p][0]:where[p][1]]]; b_ = gc[o[where[q][0]:where[q][1]]]
            out[i] = len(np.intersect1d(a_, b_, assume_unique=True)) > 0
    return out


# ------------------------------------------------------------------------------------------------ fit
def fit_windings(src, axis):
    """Fitted surface (villa's combined per-winding tifxyz) -> list of (winding_id, th, z, r) arrays."""
    x, y, z, v = read_tifxyz(src)
    meta = json.load(open(os.path.join(src, 'meta.json')))
    rng = meta.get('winding_column_ranges')
    ids = meta.get('component_winding_ids') or list(range(len(rng)))
    out = []
    for (c0, c1), wid in zip(rng, ids):
        m = v[:, c0:c1]
        if not m.any():
            continue
        xx, yy, zz = x[:, c0:c1][m], y[:, c0:c1][m], z[:, c0:c1][m]
        ax, ay = axis(zz)
        out.append((int(wid), np.mod(np.arctan2(yy - ay, xx - ax), 2 * np.pi), zz, np.hypot(xx - ax, yy - ay)))
    return out


def raster_fit(fw, nth, z0, cell, shape):
    """One fitted sheet onto the winding's (z, theta) grid: cell medians, then nearest-fill of empty cells
    inside the sheet's z extent (the fit is sampled at 20 voxels, the grid at `cell`)."""
    wid, th, zz, r = fw
    ith = np.clip((th / (2 * np.pi) * nth).astype(np.int64), 0, nth - 1)
    iz = ((zz - z0) / cell).astype(np.int64)
    ok = (iz >= 0) & (iz < shape[0])
    g = np.full(shape, np.nan, np.float32)
    s = np.zeros(shape, np.float32); c = np.zeros(shape, np.float32)
    np.add.at(s, (iz[ok], ith[ok]), r[ok]); np.add.at(c, (iz[ok], ith[ok]), 1)
    have = c > 0
    g[have] = s[have] / c[have]
    if not have.any():
        return g
    zlo, zhi = iz[ok].min(), iz[ok].max()
    idx = ndimage.distance_transform_edt(~have, return_distances=False, return_indices=True)
    g2 = g[tuple(idx)]
    g2[:zlo] = np.nan; g2[zhi + 1:] = np.nan
    return g2


def membrane(delta, known, decay_cells, levels=6, iters=60):
    """Harmonic interpolation of delta off the known cells (Dirichlet at known cells, 0 at cells farther than
    decay_cells from any known cell). Coarse-to-fine Jacobi: initialise each level from the coarser one."""
    far = ndimage.distance_transform_edt(~known) > decay_cells
    fixed = known | far
    val = np.where(known, delta, 0.0).astype(np.float64)

    def solve(val, fixed, init, n):
        u = np.where(fixed, val, init)
        for _ in range(n):
            p = np.pad(u, 1, mode='edge')
            nb = 0.25 * (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:])
            u = np.where(fixed, val, nb)
        return u

    def down(a, fx):
        H, W = a.shape
        h, w = (H + 1) // 2, (W + 1) // 2
        ap = np.zeros((2 * h, 2 * w)); fp = np.zeros((2 * h, 2 * w))
        ap[:H, :W] = a * fx; fp[:H, :W] = fx
        s = ap.reshape(h, 2, w, 2).sum((1, 3)); c = fp.reshape(h, 2, w, 2).sum((1, 3))
        return np.where(c > 0, s / np.maximum(c, 1), 0.0), c > 0

    pyr = [(val, fixed)]
    for _ in range(levels):
        v, f = pyr[-1]
        if min(v.shape) < 8:
            break
        pyr.append(down(v, f.astype(float)))
    u = np.zeros_like(pyr[-1][0])
    for li in range(len(pyr) - 1, -1, -1):
        v, f = pyr[li]
        if u.shape != v.shape:
            u = np.kron(u, np.ones((2, 2)))[:v.shape[0], :v.shape[1]]
        u = solve(v, f, u, iters * (2 if li == 0 else 1))
    return u.astype(np.float32)


# ------------------------------------------------------------------------------------------------ build
def cmd_build(a):
    t0 = time.time()
    os.makedirs(os.path.join(a.out, 'windings'), exist_ok=True)
    axis = load_axis(os.path.join(a.dataset, 'umbilicus.json'))
    K = {}
    with open(a.wrap_index) as f:
        for r in csv.DictReader(f):
            K[str(r['patch'])] = (int(float(r['k_q3c'])), float(r['thN']), str(r['component']))
    comp = a.component or max(set(v[2] for v in K.values()), key=lambda c: sum(1 for v in K.values() if v[2] == c))
    flagged, lp_pairs = set(), set()
    with open(a.flags) as f:
        for r in csv.DictReader(f):
            flagged.add(str(r['patch_a'])); flagged.add(str(r['patch_b']))
            lp_pairs.add(tuple(sorted((str(r['patch_a']), str(r['patch_b'])))))
    pitch = a.pitch_um / VOX_UM
    thr = a.conflict_frac * pitch
    _log(f'component {comp}; {len(K)} indexed patches, {len(flagged)} flagged, pitch {pitch:.2f} vox, '
         f'conflict > {thr:.2f} vox')
    P, pid_of, geom, (pzmin, pzmax) = collect_points(a.dataset, K, flagged, axis, a.handedness, comp, a.cell)
    idx_of = {p: i for i, p in pid_of.items()}
    fits = fit_windings(a.fit_source, axis) if a.fit_source else []
    fit_med = np.array([np.median(f[3]) for f in fits]) if fits else np.zeros(0)
    _log(f'{len(P)} windings with traces; {len(fits)} fitted sheets')
    zmin, zmax = pzmin, pzmax
    if fits:
        zmin = min(zmin, min(float(f[2].min()) for f in fits)); zmax = max(zmax, max(float(f[2].max()) for f in fits))
    z0 = np.floor(zmin / a.cell) * a.cell
    nz = int(np.ceil((zmax - z0) / a.cell)) + 1
    cm2_cell = (a.cell * VOX_UM * 1e-4) ** 2
    rows, geo_pairs_all, co_pairs_all = [], set(), set()
    own_cells, conf_rec, geo_of = [], [], {}
    concat_cols, labels_pts = [], []
    for w in sorted(P):
        d = P[w]
        nth, Rw = geom[w]
        shape = (nz, nth)
        ith = d['key'] % nth
        iz = d['key'] // nth - int(round(z0 / a.cell))
        # detector on ALL patches (for the comparison with the checker's flags)
        _, _, _, conf_all, pairs, groups = cell_stats(ith, iz, d['pid'], d['r'], nth, thr)
        geo_pairs_all |= {tuple(sorted((pid_of[int(p)], pid_of[int(q)]))) for p, q in np.unique(pairs, axis=0)}
        # which of the checker's flagged pairs have both patches in this winding and share a cell
        present = set(int(x) for x in np.unique(d['pid']))
        cand = [(idx_of[x], idx_of[y]) for x, y in lp_pairs if x in idx_of and y in idx_of
                and idx_of[x] in present and idx_of[y] in present]
        if cand:
            cc = colocated(groups, [c[0] for c in cand], [c[1] for c in cand])
            co_pairs_all |= {tuple(sorted((pid_of[p], pid_of[q]))) for (p, q), ok in zip(cand, cc) if ok}
        # quilt on unflagged patches
        keep = ~d['flag']
        lab = np.zeros(shape, np.uint8)
        R = np.full(shape, np.nan, np.float32)
        if keep.any():
            cs, n, rmed, conf, kpairs, kg = cell_stats(ith[keep], iz[keep], d['pid'][keep], d['r'][keep], nth, thr)
            czi, cti = cs // nth, cs % nth
            # contributing patch set per cell: order-free 64-bit hash (sum of mixed patch indices, wrapping)
            gc_k, gp_k = kg[0], kg[1]
            _, cst_k = np.unique(gc_k, return_index=True)
            with np.errstate(over='ignore'):
                hv = (gp_k.astype(np.uint64) + np.uint64(0x9E3779B97F4A7C15)) * np.uint64(0xBF58476D1CE4E5B9)
                hv ^= hv >> np.uint64(31)
                hset = np.add.reduceat(hv, cst_k)
            # up to 4 contributing patch indices per cell (groups are sorted by patch within a cell), -1 padded
            rank = np.arange(len(gc_k)) - np.repeat(cst_k, np.diff(np.append(cst_k, len(gc_k))))
            ids4 = np.full((len(cst_k), 4), -1, np.int32)
            sel_ = rank < 4
            ids4[np.repeat(np.arange(len(cst_k)), np.diff(np.append(cst_k, len(gc_k))))[sel_], rank[sel_]] = gp_k[sel_]
            tr_ = ~conf
            own_cells.append((w, czi[tr_], cti[tr_], hset[tr_], n[tr_], ids4[tr_]))
            if conf.any():
                cz_, ct_ = czi[conf], cti[conf]
                conf_rec.append((w, cz_, ct_, kpairs, kg[2][conf], kg[3][conf]))
            lab[czi[~conf], cti[~conf]] = LAB_TRACE
            R[czi[~conf], cti[~conf]] = rmed[~conf]
            lab[czi[conf], cti[conf]] = LAB_CONFLICT
        trace = lab == LAB_TRACE
        nfill = 0
        Rfit_out = np.full(shape, np.nan, np.float32)
        if fits and trace.any():
            cand = np.nonzero(np.abs(fit_med - Rw) <= 3 * pitch + 2 * np.std(d['r']))[0]
            G = [raster_fit(fits[j], nth, z0, a.cell, shape) for j in cand]
            if G:
                G = np.stack(G)                                              # (C, nz, nth)
                dif = np.abs(G - R[None])
                dif[~np.isfinite(dif)] = np.inf
                jstar = np.argmin(dif, 0)                                    # nearest fitted sheet at trace cells
                ok_t = trace & np.isfinite(np.min(dif, 0))
                idx = ndimage.distance_transform_edt(~ok_t, return_distances=False, return_indices=True)
                jall = jstar[tuple(idx)] if ok_t.any() else np.zeros(shape, int)
                Rfit = np.take_along_axis(G, jall[None], 0)[0]
                Rfit_out = Rfit.astype(np.float32)
                delta = np.where(ok_t, R - Rfit, 0.0)
                mem = membrane(delta, ok_t, a.decay_cells)
                fillable = (lab == LAB_NONE) & np.isfinite(Rfit)
                R[fillable] = (Rfit + mem)[fillable]
                lab[fillable] = LAB_FILL
                nfill = int(fillable.sum())
        # geometry
        zc = z0 + (np.arange(nz) + 0.5) * a.cell
        thc = (np.arange(nth) + 0.5) / nth * 2 * np.pi
        ax, ay = axis(zc)
        good = np.isfinite(R) & ((lab == LAB_TRACE) | (lab == LAB_FILL))
        X = np.where(good, ax[:, None] + R * np.cos(thc)[None], -1).astype(np.float32)
        Y = np.where(good, ay[:, None] + R * np.sin(thc)[None], -1).astype(np.float32)
        Z = np.where(good, np.broadcast_to(zc[:, None], shape), -1).astype(np.float32)
        wd = os.path.join(a.out, 'windings', f'w{w:+04d}')
        os.makedirs(wd, exist_ok=True)
        for nm, arr in (('x', X), ('y', Y), ('z', Z), ('label', lab), ('rfit', Rfit_out), ('r', np.where(good, R, np.nan).astype(np.float32))):
            tifffile.imwrite(os.path.join(wd, f'{nm}.tif'), arr, compression='zlib')
        json.dump(dict(format='tifxyz', type='seg', uuid=f'quilt_w{w}', scale=[1 / a.cell, 1 / a.cell],
                       winding=w, component=comp, median_radius_vox=Rw, cells=[nz, nth], z0=z0,
                       labels={'0': 'none', '1': 'trace', '2': 'fill', '3': 'conflict'}),
                  open(os.path.join(wd, 'meta.json'), 'w'), indent=1)
        concat_cols.append((X, Y, Z, lab))
        geo_of[w] = (X, Y, Z)
        row = dict(winding=w, median_radius_vox=round(Rw, 1), theta_cells=nth,
                   trace_cm2=float((lab == LAB_TRACE).sum() * cm2_cell), fill_cm2=float((lab == LAB_FILL).sum() * cm2_cell),
                   conflict_cm2=float((lab == LAB_CONFLICT).sum() * cm2_cell),
                   conflict_all_patches_cm2=float(conf_all.sum() * cm2_cell),
                   patches=int(len(np.unique(d['pid']))), unflagged_patches=int(len(np.unique(d['pid'][keep]))))
        rows.append(row)
        _log(f"w {w:+d}: R {Rw:.0f} vox, trace {row['trace_cm2']:.2f} fill {row['fill_cm2']:.2f} conflict "
             f"{row['conflict_cm2']:.3f} cm2 (all-patch conflicts {row['conflict_all_patches_cm2']:.3f})")
    # concat (theta increasing, windings ascending: w's 2 pi edge meets w+1's 0 edge), subsampled for lasagna
    st = max(1, int(round(a.concat_step / a.cell)))
    Xc = np.concatenate([c[0][::st, ::st] for c in concat_cols], 1)
    Yc = np.concatenate([c[1][::st, ::st] for c in concat_cols], 1)
    Zc = np.concatenate([c[2][::st, ::st] for c in concat_cols], 1)
    Lc = np.concatenate([c[3][::st, ::st] for c in concat_cols], 1)
    cd = os.path.join(a.out, 'concat.tifxyz')
    os.makedirs(cd, exist_ok=True)
    for nm, arr in (('x', Xc), ('y', Yc), ('z', Zc)):
        tifffile.imwrite(os.path.join(cd, f'{nm}.tif'), arr, compression='zlib')
    tifffile.imwrite(os.path.join(a.out, 'concat_label.tif'), Lc, compression='zlib')
    json.dump(dict(format='tifxyz', type='seg', uuid='quilt_concat', scale=[1 / (st * a.cell)] * 2,
                   windings=[r['winding'] for r in rows], voxel_size_um=VOX_UM),
              open(os.path.join(cd, 'meta.json'), 'w'), indent=1)
    v = Zc != -1
    np.save(os.path.join(a.out, 'labels_pts.npy'),
            np.concatenate([np.stack([Zc[v], Yc[v], Xc[v]], 1), Lc[v][:, None].astype(np.float32)], 1).astype(np.float32))
    # seams: every trace cell with its contributing-set hash (4-voxel resolution, for the render's seam map)
    op, oh, ow, on, orr, oi = [], [], [], [], [], []
    for w, cz, ct, hs, nn, i4 in own_cells:
        oi.append(i4)
        X, Y, Z = geo_of[w]
        axc, ayc = axis(Z[cz, ct].astype(np.float64))
        orr.append(np.hypot(X[cz, ct] - axc, Y[cz, ct] - ayc).astype(np.float32))
        op.append(np.stack([Z[cz, ct], Y[cz, ct], X[cz, ct]], 1)); oh.append(hs)
        ow.append(np.full(len(cz), w, np.int16)); on.append(nn.astype(np.int16))
    if op:
        np.savez(os.path.join(a.out, 'owners.npz'), pts=np.concatenate(op).astype(np.float32),
                 set_hash=np.concatenate(oh), winding=np.concatenate(ow), n_patches=np.concatenate(on),
                 r=np.concatenate(orr), ids4=np.concatenate(oi))
    # conflict cells (flagged patches dropped): location, extreme patches, radial spread
    cr = []
    for w, cz, ct, pr, rlo, rhi in conf_rec:
        nth_ = geom[w][0]
        zc_ = z0 + (cz + 0.5) * a.cell; th_ = (ct + 0.5) / nth_ * 2 * np.pi
        ax_, ay_ = axis(zc_); rr = 0.5 * (rlo + rhi)
        for i in range(len(cz)):
            cr.append(dict(winding=int(w), z=float(zc_[i]), y=float(ay_[i] + rr[i] * np.sin(th_[i])),
                           x=float(ax_[i] + rr[i] * np.cos(th_[i])), theta=float(th_[i]),
                           r_min=float(rlo[i]), r_max=float(rhi[i]),
                           patch_a=pid_of[int(pr[i][0])], patch_b=pid_of[int(pr[i][1])]))
    json.dump(cr, open(os.path.join(a.out, 'conflicts.json'), 'w'))
    # detector vs the checker's flagged joins
    L = lp_pairs
    G_ = geo_pairs_all
    CO = co_pairs_all
    tp = len(G_ & L)
    cmp = dict(geometric_conflict_pairs=len(G_), lp_flagged_pairs=len(L), both=tp,
               precision_geo_vs_lp=tp / len(G_) if G_ else None,
               recall_geo_vs_lp=tp / len(L) if L else None,
               lp_pairs_colocated_in_a_cell=len(L & CO),
               recall_geo_vs_lp_colocated=tp / len(L & CO) if (L & CO) else None,
               note='pairs = unordered patch pairs. A geometric pair is the (min r, max r) patches of a conflict cell, '
                    'detector run on ALL patches of the component. LP pairs = unsatisfied.csv rows (any type). '
                    'recall_colocated counts only LP pairs that share at least one cell in one winding (the only '
                    'ones this detector can see). Swapping reference and test swaps precision and recall.')
    tot = {k: sum(r[k] for r in rows) for k in ('trace_cm2', 'fill_cm2', 'conflict_cm2', 'conflict_all_patches_cm2')}
    res = dict(component=comp, cell_vox=a.cell, pitch_vox=pitch, conflict_threshold_vox=thr, decay_cells=a.decay_cells,
               flagged_patches=len(flagged), windings=rows, totals=tot, detector_vs_lp=cmp,
               fit_source=os.path.abspath(a.fit_source) if a.fit_source else None, wall_s=round(time.time() - t0, 1))
    json.dump(res, open(os.path.join(a.out, 'quilt.json'), 'w'), indent=1)
    T = ['# QUILT', '', f"component {comp}; cell {a.cell} vox; conflict > {thr:.1f} vox (0.6 pitch); "
         f"flagged patches dropped: {len(flagged)}", '',
         '| winding | R (vox) | trace cm² | fill cm² | conflict cm² | conflict, all patches cm² |', '|---|---|---|---|---|---|']
    for r in rows:
        T.append(f"| {r['winding']:+d} | {r['median_radius_vox']:.0f} | {r['trace_cm2']:.2f} | {r['fill_cm2']:.2f} | "
                 f"{r['conflict_cm2']:.3f} | {r['conflict_all_patches_cm2']:.3f} |")
    T.append(f"| **total** | | **{tot['trace_cm2']:.2f}** | **{tot['fill_cm2']:.2f}** | **{tot['conflict_cm2']:.3f}** | "
             f"**{tot['conflict_all_patches_cm2']:.3f}** |")
    f_ = lambda x: 'n/a' if x is None else f'{x:.3f}'
    T += ['', '## Geometric conflicts vs the checker\'s flagged joins (patch pairs)', '',
          f"- geometric conflict pairs {cmp['geometric_conflict_pairs']}, LP-flagged pairs {cmp['lp_flagged_pairs']}, both {cmp['both']}",
          f"- precision (geometric → LP) {f_(cmp['precision_geo_vs_lp'])}; recall {f_(cmp['recall_geo_vs_lp'])}; "
          f"recall among co-located LP pairs ({cmp['lp_pairs_colocated_in_a_cell']}) {f_(cmp['recall_geo_vs_lp_colocated'])}",
          '- read the other way (LP as the detector, geometry as reference): precision and recall swap.']
    open(os.path.join(a.out, 'quilt_table.md'), 'w').write('\n'.join(T) + '\n')
    _log(f"totals {tot}; detector vs LP {({k: cmp[k] for k in ('both', 'precision_geo_vs_lp', 'recall_geo_vs_lp')})}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    q = sp.add_parser('build')
    q.add_argument('--dataset', required=True)
    q.add_argument('--wrap-index', required=True)
    q.add_argument('--flags', required=True)
    q.add_argument('--fit-source', default='')
    q.add_argument('--out', required=True)
    q.add_argument('--component', default='')
    q.add_argument('--handedness', type=int, default=1)
    q.add_argument('--cell', type=float, default=4.0)
    q.add_argument('--pitch-um', type=float, default=134.0)
    q.add_argument('--conflict-frac', type=float, default=0.6)
    q.add_argument('--decay-cells', type=int, default=64)
    q.add_argument('--concat-step', type=float, default=20.0)
    a = p.parse_args(argv)
    {'build': cmd_build}[a.cmd](a)


if __name__ == '__main__':
    main()
