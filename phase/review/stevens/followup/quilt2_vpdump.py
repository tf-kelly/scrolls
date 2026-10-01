"""QUILT v2: complete Stevens' pages with the traced patches (PLAN.md addendum 5). Trace only, no fill, CPU.

  python -m vc_scale.quilt2 --tranche dataset.tgz --components s4_10_components_tifxyz.zip \
         --wrap-index wrap_index.csv --flags unsatisfied.csv --umbilicus umbilicus.json --out OUT

Streams the patch tarball twice (no extraction): pass 1 fixes each winding's median radius (its theta resolution),
pass 2 aggregates every patch into (winding, 8-voxel cell) means. Components are joined to our index vertex by vertex
(radius match to the indexed traces in the same cell), given a sheet key q = w - floor(Theta / 2 pi) along their own
unwrapped angle, and form the footprint F. Unflagged patches are classed added / redundant / conflict against F.
Writes OUT/quilt2.json, OUT/quilt2_table.md, OUT/components.csv, OUT/layout.png (+ layout_small.jpg).
"""
import argparse
import csv
import io
import json
import os
import tarfile
import time
import zipfile
from collections import defaultdict

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

VOX_UM = 7.91
TWO_PI = 2 * np.pi
SEED = 20260929


def _log(*a):
    print(f'[{time.strftime("%H:%M:%S")}]', *a, flush=True)


def cross(t1, t2):
    e = t1 + (np.mod(t2 - t1 + np.pi, TWO_PI) - np.pi)
    return np.where(e >= TWO_PI, 1, np.where(e < 0, -1, 0))


def load_axis(path):
    u = json.load(open(path))
    pts = u['control_points'] if isinstance(u, dict) else u
    cp = np.array([[p['z'], p['y'], p['x']] for p in pts], np.float64)
    cp = cp[np.argsort(cp[:, 0])]
    return lambda z: (np.interp(z, cp[:, 0], cp[:, 2]), np.interp(z, cp[:, 0], cp[:, 1]))


def upsample(x, y, z, v, f=2):
    q = v[:-1, :-1] & v[1:, :-1] & v[:-1, 1:] & v[1:, 1:]
    ii, jj = np.nonzero(q)
    out = []
    for arr in (x, y, z):
        a00, a01, a10, a11 = arr[ii, jj], arr[ii, jj + 1], arr[ii + 1, jj], arr[ii + 1, jj + 1]
        vals = []
        for u in np.arange(f) / f:
            for w in np.arange(f) / f:
                vals.append((1 - u) * (1 - w) * a00 + (1 - u) * w * a01 + u * (1 - w) * a10 + u * w * a11)
        out.append(np.concatenate(vals))
    return out


def stream_patches(tranche, K, axis, s, limit=0):
    """Yield (pid, th, z, r, w) per indexed patch (upsampled x2), streaming the tarball."""
    cur, have = None, {}
    n_done = [0]

    def emit(pid, d):
        if pid not in K or not all(c in d for c in 'xyz'):
            return None
        x, y, z = d['x'], d['y'], d['z']
        v = (x != -1) & (y != -1) & (z != -1)
        if v.sum() < 4:
            return None
        X, Y, Z = upsample(x, y, z, v)
        if not len(X):
            return None
        ax, ay = axis(Z)
        th = np.mod(np.arctan2(Y - ay, X - ax), TWO_PI)
        r = np.hypot(X - ax, Y - ay)
        k, thN, _ = K[pid]
        w = k + s * cross(np.full(th.shape, thN), th)
        return pid, th, Z, r, w

    with tarfile.open(tranche, 'r|gz') as t:
        for m in t:
            p = m.name.split('/')
            if len(p) == 4 and p[1] == 'verified_patches' and p[3] in ('x.tif', 'y.tif', 'z.tif'):
                pid = p[2]
                if pid != cur:
                    if limit and n_done[0] >= limit:
                        return
                    if cur is not None:
                        e = emit(cur, have)
                        if e:
                            n_done[0] += 1
                            yield e
                    cur, have = pid, {}
                have[p[3][0]] = tifffile.imread(io.BytesIO(t.extractfile(m).read())).astype(np.float64)
        if cur is not None:
            e = emit(cur, have)
            if e:
                yield e


def wkey(w, key):
    return (w.astype(np.int64) + 1000) << 40 | key.astype(np.int64)


def group_cells(wk, pr):
    """-> unique wkeys, n patches, mean of patch means, max-min of patch means."""
    o = np.argsort(wk, kind='stable')
    u, st = np.unique(wk[o], return_index=True)
    rs = pr[o].astype(np.float64)
    n = np.diff(np.append(st, len(o)))
    mean = np.add.reduceat(rs, st) / n
    spread = np.maximum.reduceat(rs, st) - np.minimum.reduceat(rs, st)
    return u, n, mean, spread


def lookup(sorted_keys, vals, q, fill=np.nan):
    if len(sorted_keys) == 0:
        return np.full(q.shape, fill, np.float64 if vals.dtype.kind == 'f' else vals.dtype), np.zeros(q.shape, bool)
    i = np.searchsorted(sorted_keys, q)
    i = np.clip(i, 0, len(sorted_keys) - 1)
    hit = sorted_keys[i] == q
    out = np.full(q.shape, fill, np.float64 if vals.dtype.kind == 'f' else vals.dtype)
    out[hit] = vals[i[hit]]
    return out, hit


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tranche', required=True)
    p.add_argument('--components', required=True)
    p.add_argument('--wrap-index', required=True)
    p.add_argument('--flags', required=True)
    p.add_argument('--umbilicus', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--cell', type=float, default=8.0)
    p.add_argument('--pitch-um', type=float, default=134.0)
    p.add_argument('--conflict-frac', type=float, default=0.6)
    p.add_argument('--match-frac', type=float, default=0.5)
    p.add_argument('--handedness', type=int, default=1)
    p.add_argument('--component', default='0')
    p.add_argument('--max-patches', type=int, default=0, help='debug: stop after N patches')
    p.add_argument('--only-comps', default='', help='debug: comma list of component folder names')
    a = p.parse_args(argv)
    t0 = time.time()
    os.makedirs(a.out, exist_ok=True)
    axis = load_axis(a.umbilicus)
    pitch = a.pitch_um / VOX_UM
    thr = a.conflict_frac * pitch
    C = a.cell
    cm2_cell = (C * VOX_UM * 1e-4) ** 2
    K = {}
    for r in csv.DictReader(open(a.wrap_index)):
        if str(r['component']) == a.component:
            K[str(r['patch'])] = (int(float(r['k_q3c'])), float(r['thN']), str(r['component']))
    flagged = set()
    for r in csv.DictReader(open(a.flags)):
        flagged.add(str(r['patch_a'])); flagged.add(str(r['patch_b']))
    s = a.handedness
    _log(f'{len(K)} indexed patches (component {a.component}), {len(flagged)} flagged; cell {C} vox, pitch {pitch:.2f}, '
         f'conflict > {thr:.2f} vox')

    cache = os.path.join(a.out, 'passes_cache.npz')
    if os.path.exists(cache) and not a.max_patches:
        cz_ = np.load(cache, allow_pickle=False)
        WK, PR, PI, FL = cz_['WK'], cz_['PR'], cz_['PI'], cz_['FL']
        pids = [str(x) for x in cz_['pids']]
        geom = {int(w): (int(n_), float(R_)) for w, n_, R_ in cz_['geom']}
        NZ = int(cz_['NZ'])
        _log(f'passes loaded from cache: {len(pids)} patches, {len(WK):,} rows')
    else:
        WK, PR, PI, FL, pids, geom, NZ = passes(a, K, axis, s, flagged, C)
        if not a.max_patches:
            np.savez(cache, WK=WK, PR=PR, PI=PI, FL=FL, pids=np.array(pids), NZ=NZ,
                     geom=np.array([[w, n_, R_] for w, (n_, R_) in geom.items()]))
    Uall, Nall, Rall, _ = group_cells(WK, PR)
    comp_stage(a, K, s, C, pitch, thr, cm2_cell, flagged, WK, PR, PI, FL, pids, geom, NZ, Uall, Rall, t0, axis)


def passes(a, K, axis, s, flagged, C):
    # ---------------------------------------------------------------- pass 1: winding radii
    rad = defaultdict(list)
    zmin, zmax = np.inf, -np.inf
    for n, (pid, th, Z, r, w) in enumerate(stream_patches(a.tranche, K, axis, s, a.max_patches)):
        zmin, zmax = min(zmin, Z.min()), max(zmax, Z.max())
        for wv in np.unique(w):
            m = w == wv
            rad[int(wv)].append((float(np.median(r[m])), int(m.sum())))
        if n % 10000 == 0:
            _log(f'pass 1: {n} patches')
    geom = {}
    for w, l in rad.items():
        rr = np.array([x for x, _ in l]); ww = np.array([y for _, y in l], float)
        o = np.argsort(rr); cw = np.cumsum(ww[o])
        Rw = float(rr[o][np.searchsorted(cw, cw[-1] / 2)])
        geom[w] = (max(8, int(np.ceil(TWO_PI * Rw / C))), Rw)
    NZ = int(np.ceil(zmax / C)) + 2
    _log(f'pass 1 done: {len(geom)} windings, z {zmin:.0f}-{zmax:.0f}')

    # ---------------------------------------------------------------- pass 2: (winding, cell, patch) means
    WK, PR, PI, FL = [], [], [], []
    pids = []
    for n, (pid, th, Z, r, w) in enumerate(stream_patches(a.tranche, K, axis, s, a.max_patches)):
        i = len(pids); pids.append(pid)
        for wv in np.unique(w):
            m = w == wv
            nth = geom[int(wv)][0]
            key = np.floor(Z[m] / C).astype(np.int64) * nth + np.clip((th[m] / TWO_PI * nth).astype(np.int64), 0, nth - 1)
            ks, inv = np.unique(key, return_inverse=True)
            mr = np.bincount(inv, weights=r[m]) / np.bincount(inv)
            WK.append(wkey(np.full(len(ks), wv), ks)); PR.append(mr.astype(np.float32))
            PI.append(np.full(len(ks), i, np.int32)); FL.append(np.full(len(ks), pid in flagged, bool))
        if n % 10000 == 0:
            _log(f'pass 2: {n} patches')
    WK = np.concatenate(WK); PR = np.concatenate(PR); PI = np.concatenate(PI); FL = np.concatenate(FL)
    _log(f'pass 2 done: {len(pids)} patches, {len(WK):,} (cell, patch) rows')
    return WK, PR, PI, FL, pids, geom, NZ


def comp_stage(a, K, s, C, pitch, thr, cm2_cell, flagged, WK, PR, PI, FL, pids, geom, NZ, Uall, Rall, t0, axis):

    # ---------------------------------------------------------------- components
    class _DirZip:   # VP: read the extracted components folder (same files as the zip, sha256 8af35fb6 zip)
        def __init__(self, d): self.d = d
        def namelist(self): return [f'{c}/{f}' for c in os.listdir(self.d) for f in os.listdir(os.path.join(self.d, c))]
        def read(self, n): return open(os.path.join(self.d, n), 'rb').read()
    Z_ = _DirZip(a.components) if os.path.isdir(a.components) else zipfile.ZipFile(a.components)
    comps = sorted({n.split('/')[0] for n in Z_.namelist() if n.endswith('x.tif')}, key=lambda c: int(c.split('_')[-1]))
    if a.only_comps:
        comps = [c for c in comps if c in a.only_comps.split(',')]
    wins = np.array(sorted(geom))
    comp_rows, Fk, Fr, Fc = [], [], [], []
    rng = np.random.default_rng(SEED)
    straddle_rows = []
    # dense per-winding grids of the all-trace radius for local medians (built lazily)
    dense = {}

    def dense_grid(w):
        if w not in dense:
            nth = geom[w][0]
            lo, hi = wkey(np.array([w]), np.array([0]))[0], wkey(np.array([w + 1]), np.array([0]))[0]
            i0, i1 = np.searchsorted(Uall, lo), np.searchsorted(Uall, hi)
            key = Uall[i0:i1] & ((1 << 40) - 1)
            g = np.full((NZ, nth), np.nan, np.float32)
            iz, it = key // nth, key % nth
            okk = (iz >= 0) & (iz < NZ)
            g[iz[okk], it[okk]] = Rall[i0:i1][okk]
            dense[w] = g
        return dense[w]

    def rloc(w, th, z):
        if w not in geom:
            return np.nan
        g = dense_grid(w); nth = g.shape[1]
        it = int(th / TWO_PI * nth); iz = int(z / C)
        dt = max(1, int(0.05 * nth)); dz = int(256 / C)
        cols = np.arange(it - dt, it + dt + 1) % nth
        blk = g[max(iz - dz, 0):iz + dz + 1][:, cols]
        v = blk[np.isfinite(blk)]
        return float(np.median(v)) if len(v) >= 3 else np.nan

    for ci, cname in enumerate(comps):
        tc = time.time()
        x = tifffile.imread(io.BytesIO(Z_.read(f'{cname}/x.tif'))).astype(np.float32)
        y = tifffile.imread(io.BytesIO(Z_.read(f'{cname}/y.tif'))).astype(np.float32)
        z = tifffile.imread(io.BytesIO(Z_.read(f'{cname}/z.tif'))).astype(np.float32)
        meta = json.loads(Z_.read(f'{cname}/meta.json'))
        v = (x != -1) & (y != -1) & (z != -1) & np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & ~((x == 0) & (y == 0) & (z == 0))
        sc = float(meta.get('scale', [0.25, 0.25])[0])
        cell_vox2 = (1.0 / sc) ** 2
        summed_cm2 = float(v.sum() * cell_vox2 * (VOX_UM * 1e-4) ** 2)
        H, W = v.shape
        ii, jj = np.nonzero(v)
        xv, yv, zv = x[v].astype(np.float64), y[v].astype(np.float64), z[v].astype(np.float64)
        del x, y
        ax, ay = axis(zv)
        th = np.mod(np.arctan2(yv - ay, xv - ax), TWO_PI)
        r = np.hypot(xv - ax, yv - ay)
        # per-vertex match: nearest indexed trace radius among windings at this cell
        best = np.full(len(r), np.inf); bw = np.full(len(r), -9999, np.int32)
        iz = np.floor(zv / C).astype(np.int64)
        for w in wins:
            nth, Rw = geom[int(w)]
            m = np.abs(r - Rw) < 0.35 * Rw + 150   # pre-filter: a winding's radius varies with theta and z around Rw
            if not m.any():
                continue
            key = iz[m] * nth + np.clip((th[m] / TWO_PI * nth).astype(np.int64), 0, nth - 1)
            rv, hit = lookup(Uall, Rall, wkey(np.full(m.sum(), w), key))
            d = np.abs(r[m] - rv)
            d[~hit] = np.inf
            idx = np.nonzero(m)[0]
            better = d < best[idx]
            best[idx[better]] = d[better]; bw[idx[better]] = w
        matched = best <= a.match_frac * pitch
        if os.environ.get('Q2_DEBUG'):
            fin = np.isfinite(best)
            _log(f'  debug {cname}: vertices {len(best)}, any cell hit {fin.mean():.3f}, best-dist pct 10/50/90 '
                 f'{np.percentile(best[fin], [10, 50, 90]) if fin.any() else None}')
        # grid of winding, nearest matched vertex for the rest
        G = np.full((H, W), -9999, np.int32)
        G[ii[matched], jj[matched]] = bw[matched]
        if matched.any():
            miss = np.ones((H, W), bool); miss[ii[matched], jj[matched]] = False
            nidx = ndimage.distance_transform_edt(miss, return_distances=False, return_indices=True)
            wv = G[nidx[0][ii, jj], nidx[1][ii, jj]]
            del nidx, miss
        else:
            wv = np.full(len(r), -9999, np.int32)
        # unwrapped angle along the component's unrolled axis
        Th = np.full((H, W), np.nan); Th[ii, jj] = th

        def unwrap_axis(axis_):
            c = np.nanmean(np.cos(Th), axis=1 - axis_) if True else None
            sn = np.nanmean(np.sin(Th), axis=1 - axis_)
            ang = np.arctan2(sn, c)
            ok = np.isfinite(ang)
            if ok.sum() < 2:
                return None, 0.0
            idx_ = np.arange(len(ang))
            ang_f = np.interp(idx_, idx_[ok], np.unwrap(ang[ok]))
            return ang_f, float(np.ptp(ang_f[ok]))
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            a_c, span_c = unwrap_axis(1)       # along columns
            a_r, span_r = unwrap_axis(0)       # along rows
        use_cols = span_c >= span_r
        base = a_c[jj] if use_cols else a_r[ii]
        Theta = base + (np.mod(th - base + np.pi, TWO_PI) - np.pi)
        q = np.where(wv > -9999, wv - s * np.floor(Theta / TWO_PI).astype(np.int64), -99999)
        if os.environ.get('VP_DUMP'):   # VP-M21 follow-up: per-vertex winding and sheet key, no change to the rule
            np.savez_compressed(os.path.join(os.environ['VP_DUMP'], f'{cname}_q.npz'), ii=ii, jj=jj, wv=wv, q=q,
                                matched=matched, bw=bw, best=best, Theta=Theta)
        qm = q[matched]
        cnt = defaultdict(int)
        for kq, c_ in zip(*np.unique(qm, return_counts=True)):
            cnt[int(kq)] = int(c_)
        tot_m = max(sum(cnt.values()), 1)
        qmod = max(cnt, key=cnt.get) if cnt else None
        spanned = sorted(k for k, c_ in cnt.items() if c_ / tot_m >= 0.05)
        # footprint cells
        okw = np.isin(wv, wins)
        keys = np.zeros(len(r), np.int64)
        for w in np.unique(wv[okw]):
            m = wv == w
            nth = geom[int(w)][0]
            keys[m] = iz[m] * nth + np.clip((th[m] / TWO_PI * nth).astype(np.int64), 0, nth - 1)
        fk = wkey(wv[okw], keys[okw])
        Fk.append(fk); Fr.append(r[okw].astype(np.float32)); Fc.append(np.full(okw.sum(), ci, np.int16))
        row = dict(component=cname, uuid=meta.get('uuid'), grid=[H, W], summed_cm2=summed_cm2,
                   vertices=int(len(r)), matched_share=float(matched.mean()), footprint_cells=int(len(np.unique(fk))),
                   footprint_cm2=float(len(np.unique(fk)) * cm2_cell), modal_sheet=qmod,
                   modal_share=cnt[qmod] / tot_m if qmod is not None else None, sheets_ge5pct=spanned,
                   straddling=len(spanned) >= 2, turns=float(np.ptp(Theta) / TWO_PI),
                   z_range=[float(zv.min()), float(zv.max())], unrolled_axis='columns' if use_cols else 'rows',
                   windings=[int(w) for w in np.unique(wv[okw])])
        # straddle radius test (VM-A-M11 rule), edges between the modal sheet and another, both matched
        if row['straddling']:
            Q = np.full((H, W), -99999, np.int64); Q[ii[matched], jj[matched]] = qm
            Wg = np.full((H, W), -9999, np.int64); Wg[ii, jj] = wv
            Rg = np.full((H, W), np.nan); Rg[ii, jj] = r
            Tg = np.full((H, W), np.nan); Tg[ii, jj] = Theta
            Zg = np.full((H, W), np.nan); Zg[ii, jj] = zv
            edges = []
            for (sa, sb) in (((slice(None), slice(0, -1)), (slice(None), slice(1, None))),
                             ((slice(0, -1), slice(None)), (slice(1, None), slice(None)))):
                qa, qb = Q[sa], Q[sb]
                m = (qa > -99999) & (qb > -99999) & (qa != qb) & ((qa == qmod) | (qb == qmod))
                ya, xa = np.nonzero(m)
                off = (0, 1) if sa[0] == slice(None) else (1, 0)
                for y0, x0 in zip(ya, xa):
                    # the non-modal side is tested; the modal-side neighbour is kept for the section direction
                    if qa[y0, x0] == qmod:
                        edges.append((y0 + off[0], x0 + off[1], y0, x0))
                    else:
                        edges.append((y0, x0, y0 + off[0], x0 + off[1]))
            seen_ = {}
            for e in edges:                      # one per tested vertex, first seen (the original order)
                seen_.setdefault(e[:2], e)
            edges = list(seen_.values())
            if len(edges) > 2000:
                edges = [edges[i] for i in rng.choice(len(edges), 2000, replace=False)]
            cls = defaultdict(int)
            sep = []
            rec_e = []
            for (yy, xx, ym, xm) in edges:
                kp = int(Wg[yy, xx]); Th_v = Tg[yy, xx]
                km = int(qmod + s * np.floor(Th_v / TWO_PI))
                thv = float(np.mod(Th_v, TWO_PI)); zz = float(Zg[yy, xx]); rho = float(Rg[yy, xx])
                rp, rq = rloc(kp, thv, zz), rloc(km, thv, zz)
                if not (np.isfinite(rp) and np.isfinite(rq)) or kp == km:
                    cls['undetermined'] += 1; rec_e.append((yy, xx, ym, xm, kp, km, 0)); continue
                pl = abs(rp - rq) / abs(kp - km)
                sep.append(pl / pitch)
                d_own, d_mod = abs(rho - rp), abs(rho - rq)
                if d_own < d_mod - 0.25 * pl:
                    cls['page_off_sheet_his_switch'] += 1; code = 1
                elif d_mod < d_own - 0.25 * pl:
                    cls['index_off_sheet_our_index'] += 1; code = 2
                else:
                    cls['undetermined'] += 1; code = 0
                rec_e.append((yy, xx, ym, xm, kp, km, code))
            row['straddle_edges_tested'] = len(edges)
            np.save(os.path.join(a.out, f'straddle_edges_{cname}.npy'), np.array(rec_e, np.int64).reshape(-1, 7))
            sp_ = np.array(sep) if sep else np.zeros(0)
            # POST-HOC diagnostic (not registered): local separation of the two windings' traces at the straddle, in
            # pitches. ~1 = our index separates two real sheets there (the page crossed a sheet); < 0.5 = the index
            # gives one physical sheet two labels there.
            row['posthoc_local_separation_pitches'] = dict(
                n=int(len(sp_)), median=float(np.median(sp_)) if len(sp_) else None,
                share_lt_0p5=float((sp_ < 0.5).mean()) if len(sp_) else None,
                share_0p5_to_1p5=float(((sp_ >= 0.5) & (sp_ <= 1.5)).mean()) if len(sp_) else None,
                share_gt_1p5=float((sp_ > 1.5).mean()) if len(sp_) else None)
            row['straddle_classes'] = dict(cls)
            dec = {k: v for k, v in cls.items() if k != 'undetermined'}
            row['straddle_side'] = max(dec, key=dec.get) if dec else 'undetermined'
            del Q, Wg, Rg, Tg, Zg
        comp_rows.append(row)
        _log(f"{cname}: {summed_cm2:.2f} cm2 summed, matched {row['matched_share']:.3f}, sheets {spanned}, "
             f"turns {row['turns']:.2f}, footprint {row['footprint_cm2']:.2f} cm2 ({time.time() - tc:.0f}s)"
             + (f", straddle {row.get('straddle_classes')}" if row['straddling'] else ''))
        del G, Th, xv, yv, zv, th, r, z

    # ---------------------------------------------------------------- footprint F and patch classes
    Fk = np.concatenate(Fk); Fr = np.concatenate(Fr); Fc = np.concatenate(Fc)
    o = np.argsort(Fk, kind='stable')
    FU, fst = np.unique(Fk[o], return_index=True)
    FR = np.add.reduceat(Fr[o].astype(np.float64), fst) / np.diff(np.append(fst, len(o)))
    FC = Fc[o][fst]
    del Fk, Fr, Fc, o
    unf = ~FL
    wk_u, pr_u, pi_u = WK[unf], PR[unf], PI[unf]
    rF, inF = lookup(FU, FR, wk_u)
    dis = inF & (np.abs(pr_u - rF) > thr)
    npat = len(pids)
    touch = np.bincount(pi_u[inF], minlength=npat) > 0
    bad = np.bincount(pi_u[dis], minlength=npat) > 0
    isun = np.bincount(pi_u, minlength=npat) > 0
    cls_added = isun & ~touch
    cls_red = isun & touch & ~bad
    cls_conf = isun & bad

    def net(mask_rows):
        u, n_, _, spread = group_cells(wk_u[mask_rows], pr_u[mask_rows])
        conf = (n_ >= 2) & (spread > thr)
        return u, conf

    ua, ca = net(cls_added[pi_u])
    added_net_cm2 = float((~ca).sum() * cm2_cell)
    uc, cc = net(~inF)
    cell_level_cm2 = float((~cc).sum() * cm2_cell)
    ub, cb = net(np.ones(len(wk_u), bool))
    upper_cm2 = float((~cb).sum() * cm2_cell)
    dis_cells = np.unique(wk_u[dis])

    def patch_area(mask):
        return float(np.isin(pi_u, np.nonzero(mask)[0]).sum() * cm2_cell)

    res = dict(
        inputs=dict(tranche=os.path.abspath(a.tranche), components=os.path.abspath(a.components), wrap_index=a.wrap_index,
                    flags=a.flags, umbilicus=a.umbilicus),
        cell_vox=C, pitch_vox=pitch, conflict_threshold_vox=thr, match_threshold_vox=a.match_frac * pitch,
        patches_indexed=npat, patches_flagged_in_component=int(sum(1 for p_ in pids if p_ in flagged)),
        a=dict(summed_x1_cm2=sum(r_['summed_cm2'] for r_ in comp_rows), footprint_cm2=float(len(FU) * cm2_cell),
               matched_share=float(np.average([r_['matched_share'] for r_ in comp_rows],
                                                 weights=[r_['vertices'] for r_ in comp_rows]))),
        b=dict(added_net_cm2=added_net_cm2, added_conflict_cells_cm2=float(ca.sum() * cm2_cell),
               cell_level_net_cm2=cell_level_cm2, upper_bound_raw_quilt_cm2=upper_cm2,
               upper_bound_conflict_cm2=float(cb.sum() * cm2_cell)),
        c=dict(straddling=sum(1 for r_ in comp_rows if r_['straddling']),
               sides={r_['component']: r_.get('straddle_side') for r_ in comp_rows if r_['straddling']}),
        d=dict(patches_touching_F=int(touch.sum()), conflict_patches=int(cls_conf.sum()),
               conflict_share_of_touching=float(cls_conf.sum() / max(touch.sum(), 1)),
               redundant_patches=int(cls_red.sum()), added_patches=int(cls_added.sum()),
               disagreeing_cells_in_F_cm2=float(len(dis_cells) * cm2_cell),
               conflict_patches_summed_cm2=patch_area(cls_conf), redundant_patches_summed_cm2=patch_area(cls_red),
               added_patches_summed_cm2=patch_area(cls_added)),
        components=comp_rows, wall_s=round(time.time() - t0, 1))
    json.dump(res, open(os.path.join(a.out, 'quilt2.json'), 'w'), indent=1)
    with open(os.path.join(a.out, 'components.csv'), 'w', newline='') as f:
        cols = ['component', 'summed_cm2', 'footprint_cm2', 'matched_share', 'modal_sheet', 'modal_share', 'sheets_ge5pct',
                'straddling', 'straddle_side', 'straddle_classes', 'turns', 'z_range', 'unrolled_axis']
        wr = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore'); wr.writeheader()
        for r_ in comp_rows:
            wr.writerow({k: r_.get(k) for k in cols})
    _log(json.dumps({k: res[k] for k in ('a', 'b', 'c', 'd')}))

    # ---------------------------------------------------------------- layout figure
    layout(a.out, geom, NZ, C, FU, FC, ua[~ca], np.concatenate([ua[ca], dis_cells]), len(comps))
    _log(f'done in {time.time() - t0:.0f}s')


def layout(out, geom, NZ, C, FU, FC, added, conflict, ncomp, width=1600, row_h=170):
    """One row per winding: theta 0 -> 2 pi across, z up. Cells are pooled over z blocks by priority
    (conflict > page > added) and each theta cell fills its whole pixel span."""
    pal = [(230, 25, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240),
           (240, 50, 230), (210, 245, 60), (250, 190, 212), (170, 110, 40)][:ncomp]
    lut = np.zeros((256, 3), np.uint8)
    lut[1] = (40, 200, 90)
    for i, c in enumerate(pal):
        lut[2 + i] = c
    lut[200] = (255, 255, 255)
    wins = sorted(geom)

    def split(keys):
        return (keys >> 40) - 1000, keys & ((1 << 40) - 1)

    fw, fk = split(FU)
    aw, ak = split(added)
    cw, ck = split(conflict)
    zs = max(1, int(np.ceil(NZ / row_h)))
    nzb = -(-NZ // zs)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 13) \
        if os.path.exists('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf') else ImageFont.load_default()
    rows = []
    used = [w for w in wins if (fw == w).any() or (aw == w).any()]
    for w in used:
        nth = geom[w][0]
        L = np.zeros((nzb, nth), np.uint8)

        def put(k, code):
            iz, it = k // nth, k % nth
            ok = (iz >= 0) & (iz < NZ)
            np.maximum.at(L, (iz[ok] // zs, it[ok]), np.uint8(code))
        put(ak[aw == w], 1)
        m = fw == w
        for c in range(ncomp):
            put(fk[m][FC[m] == c], 2 + c)
        put(ck[cw == w], 200)
        cols = (np.arange(width) * nth // width).astype(int)
        img = lut[L[::-1][:, cols]]
        hi = Image.new('RGB', (width, 16), (0, 0, 0))
        ImageDraw.Draw(hi).text((4, 1), f'winding {w:+d}  (median R {geom[w][1]:.0f} vox = {geom[w][1] * VOX_UM / 1e4:.2f} cm; '
                                        f'theta 0 -> 2 pi, {TWO_PI * geom[w][1] * VOX_UM / 1e4:.1f} cm around; z up)',
                                fill=(230, 230, 230), font=font)
        rows.append(np.concatenate([np.asarray(hi), img, np.zeros((4, width, 3), np.uint8)], 0))
    leg = Image.new('RGB', (width, 40), (0, 0, 0)); d = ImageDraw.Draw(leg); x = 4
    for i, c in enumerate(pal):
        d.rectangle([x, 12, x + 12, 24], fill=c); d.text((x + 16, 10), f'page {i}', fill=(230, 230, 230), font=font); x += 70
    for c, t in (((40, 200, 90), 'added (patches outside his pages)'), ((255, 255, 255), 'conflict')):
        d.rectangle([x, 12, x + 12, 24], fill=c); d.text((x + 16, 10), t, fill=(230, 230, 230), font=font); x += 250
    fig = np.concatenate([np.asarray(leg)] + rows, 0)
    Image.fromarray(fig).save(os.path.join(out, 'layout.png'))
    sm = Image.fromarray(fig); s_ = min(1.0, 1400 / sm.size[0])
    sm.resize((int(sm.size[0] * s_), int(sm.size[1] * s_)), Image.LANCZOS).save(os.path.join(out, 'layout_small.jpg'), quality=88)


if __name__ == '__main__':
    main()
