"""RENDER: sample a (flattened) tifxyz surface in a zarr volume, in parallel column tiles.
Pure Python (numpy/scipy); replaces vc_render_tifxyz on machines without the C++ tools.

  python -m vc_scale.render picture --surface FLAT --volume CT_URL --out DIR --umbilicus U \
         [--level 2] [--quads PLACE_ARM_DIR/quad_cn.npy] [--crops 2 --crop-px 2048]
  python -m vc_scale.render inkzarr --surface FLAT --volume INK_URL --axes yxz --out DIR --umbilicus U [--step 2]
  python -m vc_scale.render layers  --surface FLAT --volume CT_URL --out DIR --umbilicus U --zband 5622:5878

Geometry and conventions
  * The surface grid (cells of `step` voxels, meta.json scale = 1/step) is resampled bilinearly
    to output pixels of `pixel` level-0 voxels (a pixel is invalid if any grid corner is).
  * Normals: dP/dcol x dP/drow on the grid, smoothed, oriented INWARD (toward the umbilicus)
    with ONE sign per connected component, voted over vertices > 500 vox from the axis (all
    vertices if fewer than 100 such; recorded as weak). Handedness h = sign(raw . inward);
    a component with h = -1 is flipped left-right at the source (columns reversed) so text
    reads unmirrored, and the flip is recorded.
  * Unavailable data (missing chunk, outside volume) stays NaN, drawn black in PNGs and
    counted in the JSON; it is never treated as dark papyrus.

picture : level-L texture of the WHOLE surface (mean of offsets -1,0,+1 level-L voxels along the
          normal), uncropped; support map from PLACE's quad centres/normals: per pixel the
          distance along the nearest traced quad's normal (on <= 1.5 vox, near <= 8 vox, else
          none); two level-0 crops chosen by rule (max on-share window; min on-share window among
          windows with >= 50 % on+near). Outputs texture.png/.tif, support.png, overlay.png,
          strip rows (overview.jpg), crops/, picture.json.
inkzarr : max over offsets -2..+2 of a 3-D ink-prediction volume (render_ink.py's convention:
          5 slices, max composite, /p95), whole surface at `--step` vox/pixel (or a z band).
layers  : level-0 layers k = 0..64 at offset k-32 along the inward normal, uint8 = CT/257, for the
          pixels whose z lies in the band; writes layers/NN.tif, mask.png, layers.json.
"""
import argparse
import json
import multiprocessing as mp
import os
import time

import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage

from .zarrio import ZarrArray

Image.MAX_IMAGE_PIXELS = None
FAR_VOX = 500.0


# ---------------------------------------------------------------------------------- surface
def load_surface(path):
    with open(os.path.join(path, 'meta.json')) as f:
        meta = json.load(f)
    x = tifffile.imread(os.path.join(path, 'x.tif')).astype(np.float32)
    y = tifffile.imread(os.path.join(path, 'y.tif')).astype(np.float32)
    z = tifffile.imread(os.path.join(path, 'z.tif')).astype(np.float32)
    valid = (x != -1) & (y != -1) & (z != -1) & np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    mp_ = os.path.join(path, 'mask.tif')
    if os.path.exists(mp_):
        m = tifffile.imread(mp_)
        m = m[..., 0] if m.ndim == 3 else m
        if m.shape == valid.shape:
            valid &= m != 0
    zyx = np.stack([z, y, x], -1)
    zyx[~valid] = np.nan
    step = 1.0 / float(meta.get('scale', [1.0, 1.0])[0])
    return zyx, meta, step


def load_umbilicus(path):
    with open(path) as f:
        u = json.load(f)
    pts = u['control_points'] if isinstance(u, dict) and 'control_points' in u else u
    arr = np.array([[p['z'], p['y'], p['x']] if isinstance(p, dict) else p for p in pts], np.float64)
    arr = arr[np.argsort(arr[:, 0])]
    return arr[:, 0], arr[:, 1:]


def raw_normals(zyx):
    valid = np.isfinite(zyx).all(-1)
    P = np.where(valid[..., None], zyx, 0.0)
    gc = np.gradient(P, axis=1)
    gr = np.gradient(P, axis=0)
    n = np.cross(gc, gr)
    n = np.stack([ndimage.gaussian_filter(n[..., k] * valid, 1.0) for k in range(3)], -1)
    nn = np.linalg.norm(n, axis=-1, keepdims=True)
    n = n / np.maximum(nn, 1e-9)
    n[~valid] = np.nan
    return n


def orient(zyx, umb):
    """Inward normals with one sign per 8-connected component; handedness flip at the source.
    Returns (zyx, normals, record); zyx is column-reversed if the (single largest-area
    weighted) handedness is -1."""
    uz, uyx = load_umbilicus(umb)
    rec = dict(components=[])

    def once(zyx):
        n = raw_normals(zyx)
        valid = np.isfinite(n).all(-1)
        lab, nl = ndimage.label(valid, structure=np.ones((3, 3)))
        ax = np.stack([np.interp(zyx[..., 0], uz, uyx[:, 0]), np.interp(zyx[..., 0], uz, uyx[:, 1])], -1)
        towards = np.sum(n[..., 1:] * (ax - zyx[..., 1:]), -1)
        dist = np.linalg.norm(zyx[..., 1:] - ax, axis=-1)
        comps, hsum = [], 0.0
        for c in range(1, nl + 1):
            m = lab == c
            far = m & (dist > FAR_VOX)
            sel = far if far.sum() >= 100 else m
            s = 1.0 if (towards[sel] > 0).mean() >= 0.5 else -1.0
            n[m] *= s
            comps.append(dict(component=c, cells=int(m.sum()), inward_sign_of_raw=int(s),
                              vote='far' if sel is far else 'WEAK(all)',
                              vote_frac=round(float((towards[sel] * s > 0).mean()), 4)))
            hsum += s * m.sum()
        return n, comps, (1 if hsum >= 0 else -1)

    n, comps, h = once(zyx)
    rec['handedness_as_received'] = h
    rec['components'] = comps
    rec['flipped_columns'] = False
    if h < 0:
        zyx = zyx[:, ::-1].copy()
        n, comps2, h2 = once(zyx)
        rec['flipped_columns'] = True
        rec['components_after_flip'] = comps2
        rec['handedness_written'] = h2
    else:
        rec['handedness_written'] = h
    rec['mixed_components'] = int(sum(1 for c in (rec.get('components_after_flip') or comps)
                                      if c['inward_sign_of_raw'] < 0))
    return zyx, n, rec


# ---------------------------------------------------------------------------------- tiles
_G = {}


def _winit(src, nrm, url, axes, cache, mem_chunks, layer_paths=None, mask_path=None, col0=0):
    _G['src'], _G['nrm'] = src, nrm
    _G['vol'] = ZarrArray(url, axes=axes, cache_dir=cache, mem_chunks=mem_chunks)
    if layer_paths:
        _G['layer_files'] = [tifffile.memmap(p, mode='r+') for p in layer_paths]
        _G['mask_file'] = tifffile.memmap(mask_path, mode='r+')
        _G['col0'] = col0
    else:
        _G['layer_files'] = None


def _grid_tile(r0, r1, c0, c1, f):
    """Output pixels rows [r0,r1) cols [c0,c1) at `f` output px per grid cell -> zyx, normals."""
    src, nrm = _G['src'], _G['nrm']
    rr = np.arange(r0, r1) / f
    cc = np.arange(c0, c1) / f
    R, C = np.meshgrid(rr, cc, indexing='ij')
    lo = max(int(np.floor(cc[0])) - 1, 0)
    hi = min(int(np.ceil(cc[-1])) + 2, src.shape[1])
    lr = max(int(np.floor(rr[0])) - 1, 0)
    hr = min(int(np.ceil(rr[-1])) + 2, src.shape[0])
    sub, subn = src[lr:hr, lo:hi], nrm[lr:hr, lo:hi]
    coords = [R - lr, C - lo]
    P = np.stack([ndimage.map_coordinates(sub[..., k], coords, order=1, mode='nearest', cval=np.nan)
                  for k in range(3)], -1)
    N = np.stack([ndimage.map_coordinates(subn[..., k], coords, order=1, mode='nearest', cval=np.nan)
                  for k in range(3)], -1)
    N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-9)
    return P, N


def _wtile(args):
    r0, r1, c0, c1, f, offsets, scale, combine, zband = args
    P, N = _grid_tile(r0, r1, c0, c1, f)
    vol = _G['vol']
    ok = np.isfinite(P).all(-1) & np.isfinite(N).all(-1)
    if zband is not None:
        ok &= (P[..., 0] >= zband[0]) & (P[..., 0] < zband[1])
    shape = P.shape[:2]
    pts, nn = P[ok], N[ok]
    vals = np.full((len(offsets), ok.sum()), np.nan, np.float32)
    for i, k in enumerate(offsets):
        vals[i] = vol.sample((pts + k * nn) * scale)
    with np.errstate(all='ignore'):
        if combine == 'mean':
            v = np.nanmean(vals, 0) if len(offsets) > 1 else vals[0]
            v[np.isnan(vals).any(0)] = np.nan
            out = np.full(shape, np.nan, np.float32)
            out[ok] = v
        elif combine == 'max':
            v = np.nanmax(vals, 0)
            out = np.full(shape, np.nan, np.float32)
            out[ok] = v
        else:   # layers -> uint8 stack, 0 where unavailable, plus mask
            u8 = np.clip(np.rint(np.nan_to_num(vals, nan=0.0) / 257.0), 0, 255).astype(np.uint8)
            m = np.zeros(shape, np.uint8)
            m[ok] = ~np.isnan(vals).any(0)
            files = _G.get('layer_files')
            if files is not None:   # write this tile straight into the shared file-backed layers
                cc0 = c0 - _G['col0']
                t = np.zeros(shape, np.uint8)
                for i, mm in enumerate(files):
                    t[:] = 0
                    t[ok] = u8[i]
                    mm[:, cc0:cc0 + shape[1]] = t
                    mm.flush()
                _G['mask_file'][:, cc0:cc0 + shape[1]] = m
                _G['mask_file'].flush()
                return (r0, c0, None, None, vol.stats.copy())
            out = np.zeros((len(offsets),) + shape, np.uint8)
            for i in range(len(offsets)):
                out[i][ok] = u8[i]
            return (r0, c0, out, m, vol.stats.copy())
    return (r0, c0, out, None, vol.stats.copy())


def render_grid(src, nrm, f, offsets, url, axes, cache, level_scale, combine, workers, tile=1024,
                rows=None, cols=None, zband=None, mem_chunks=384, layer_paths=None, mask_path=None):
    H = int(np.floor((src.shape[0] - 1) * f)) + 1
    W = int(np.floor((src.shape[1] - 1) * f)) + 1
    r0, r1 = rows if rows else (0, H)
    q0, q1 = cols if cols else (0, W)
    r1, q1 = min(r1, H), min(q1, W)
    jobs = [(r0, r1, c, min(c + tile, q1), f, offsets, level_scale, combine, zband) for c in range(q0, q1, tile)]
    if combine == 'layers':
        # file-backed per-layer arrays when given (memory stays small at any band size)
        out = None if layer_paths else np.zeros((len(offsets), r1 - r0, q1 - q0), np.uint8)
        mask = None if layer_paths else np.zeros((r1 - r0, q1 - q0), bool)
    else:
        out = np.full((r1 - r0, q1 - q0), np.nan, np.float32)
        mask = None
    stats = {}
    ctx = mp.get_context('fork')
    with ctx.Pool(workers, initializer=_winit,
                  initargs=(src, nrm, url, axes, cache, mem_chunks, layer_paths, mask_path, q0)) as pool:
        for n, (rr, cc, o, m, st) in enumerate(pool.imap_unordered(_wtile, jobs)):
            cc -= q0
            if combine == 'layers':
                if o is not None:
                    out[:, :, cc:cc + o.shape[-1]] = o
                    mask[:, cc:cc + o.shape[-1]] = m
            else:
                out[:, cc:cc + o.shape[-1]] = o
            for k, v in st.items():
                stats[k] = max(stats.get(k, 0), v)
            if n % max(1, len(jobs) // 20) == 0:
                print(f'  tile {n + 1}/{len(jobs)}', flush=True)
    return out, mask, stats


# ---------------------------------------------------------------------------------- images
def stretch(img, lo_pct=1.0, hi_pct=99.0):
    v = img[np.isfinite(img)]
    if v.size == 0:
        return np.zeros(img.shape, np.uint8), (None, None)
    lo, hi = np.percentile(v, lo_pct), np.percentile(v, hi_pct)
    o = np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1) * 255
    o[~np.isfinite(img)] = 0
    return o.astype(np.uint8), (float(lo), float(hi))


def fold_strip(img, width, gap=8, fill=0):
    """Cut a very wide image into rows of `width` px stacked vertically (nothing dropped)."""
    H, W = img.shape[:2]
    n = -(-W // width)
    shp = (n * (H + gap) - gap, width) + img.shape[2:]
    out = np.full(shp, fill, img.dtype)
    for i in range(n):
        seg = img[:, i * width:(i + 1) * width]
        out[i * (H + gap):i * (H + gap) + H, :seg.shape[1]] = seg
    return out


def jpeg_fold(H, W, width, limit=65500, gap=8):
    """(fold width, downsample, _) so that the folded strip fits JPEG's per-side limit."""
    sc = 1
    while True:
        h, w_ = -(-H // sc), -(-W // sc)
        fw = width
        while fw < w_ and (-(-w_ // fw)) * (h + gap) - gap > limit:
            fw *= 2
        if min(fw, w_) <= limit and (-(-w_ // fw)) * (h + gap) - gap <= limit:
            return fw, sc, None
        sc *= 2


def save_png(a, path):
    Image.fromarray(a).save(path, optimize=False, compress_level=3)


# ---------------------------------------------------------------------------------- support
def support_distance(P, quad_cn_path, k=4, max_inplane=4.0):
    """Per output pixel: |distance along the nearest traced quads' normals| (vox), NaN if no
    quad centre within 16 vox. Uses PLACE's quad centres/normals (villa's loaded patches)."""
    from scipy.spatial import cKDTree
    q = np.load(quad_cn_path, mmap_mode='r')
    ok = np.isfinite(P).all(-1)
    pts = P[ok].astype(np.float32)
    lo, hi = pts.min(0) - 16, pts.max(0) + 16
    t0 = time.time()
    keep = np.ones(len(q), bool)
    for d in range(3):
        keep &= (q[:, d] >= lo[d]) & (q[:, d] <= hi[d])
    qc = np.asarray(q[keep, :3], np.float32)
    qn = np.asarray(q[keep, 3:], np.float32)
    print(f'  support: KD-tree over {len(qc):,} quad centres', flush=True)
    tree = cKDTree(qc, balanced_tree=False, compact_nodes=False)
    res = np.full(len(pts), np.nan, np.float32)
    for b in range(0, len(pts), 1 << 23):            # bounded memory: 8 M query points per block
        pb = pts[b:b + (1 << 23)]
        d, j = tree.query(pb, k=k, distance_upper_bound=16.0, workers=-1)
        best = np.full(len(pb), np.inf, np.float32)
        for i in range(k):
            hit = np.isfinite(d[:, i])
            if not hit.any():
                continue
            jj = j[hit, i]
            v = pb[hit] - qc[jj]
            perp = np.abs(np.sum(v * qn[jj], -1))
            inpl = np.sqrt(np.maximum(np.sum(v * v, -1) - perp ** 2, 0))
            cand = np.where(inpl <= max_inplane, perp, np.inf)
            idx = np.nonzero(hit)[0]
            best[idx] = np.minimum(best[idx], cand)
        anyq = np.isfinite(d[:, 0])
        rb = res[b:b + len(pb)]
        rb[anyq] = np.where(np.isfinite(best[anyq]), best[anyq], 16.0)
        del d, j
    out = np.full(P.shape[:2], np.nan, np.float32)
    out[ok] = res
    print(f'  support: done in {time.time() - t0:.0f}s', flush=True)
    return out


SUPPORT_COLORS = {'on': (40, 200, 90), 'near': (240, 170, 30), 'none': (200, 40, 40), 'off': (0, 0, 0)}


def support_classes(dist, valid, on=1.5, near=8.0):
    cls = np.full(dist.shape, 3, np.uint8)        # 3 = no surface
    cls[valid] = 2                                # none: no trace within 16 vox
    cls[valid & np.isfinite(dist) & (dist <= near)] = 1
    cls[valid & np.isfinite(dist) & (dist <= on)] = 0
    return cls


def classes_rgb(cls):
    lut = np.array([SUPPORT_COLORS['on'], SUPPORT_COLORS['near'], SUPPORT_COLORS['none'], SUPPORT_COLORS['off']], np.uint8)
    return lut[cls]


def window_pick(cls, win):
    """Top-left of the win x win window with max on-share, and of the one with min on-share among
    windows with >= 50 % on+near (patches present). Windows on a win/2 grid, >= 50 % surface."""
    H, W = cls.shape
    on = np.pad((cls == 0).astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    pr = np.pad((cls <= 1).astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    va = np.pad((cls <= 2).astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    S = lambda I, y, x: I[y + win, x + win] - I[y, x + win] - I[y + win, x] + I[y, x]
    best, worst = None, None
    win = min(win, H, W)
    step = max(1, win // 2)
    for y in range(0, max(H - win, 0) + 1, step):
        for x in range(0, max(W - win, 0) + 1, step):
            v = S(va, y, x)
            if v < 0.5 * win * win:
                continue
            fo, fp = S(on, y, x) / v, S(pr, y, x) / v
            if best is None or fo > best[0]:
                best = (fo, y, x, fp)
            if fp >= 0.5 and (worst is None or fo < worst[0]):
                worst = (fo, y, x, fp)
    return best, worst


# ---------------------------------------------------------------------------------- commands
def _common(a):
    zyx, meta, step = load_surface(a.surface)
    zyx, n, orec = orient(zyx, a.umbilicus)
    return zyx, n, orec, meta, step


def cmd_picture(a):
    t0 = time.time()
    os.makedirs(a.out, exist_ok=True)
    zyx, n, orec, meta, step = _common(a)
    pix = float(2 ** a.level)
    f = step / pix
    url = a.volume.rstrip('/') + f'/{a.level}'
    cache = os.path.join(a.cache, f'L{a.level}') if a.cache else None
    offs = [-pix, 0.0, pix]
    print(f'picture: grid {zyx.shape[:2]} step {step} vox -> {pix} vox/px (x{f:g}); level {a.level}', flush=True)
    tex, _, st = render_grid(zyx, n, f, offs, url, 'zyx', cache, 1.0 / pix, 'mean', a.workers)
    tifffile.imwrite(os.path.join(a.out, 'texture.tif'), tex, compression='zlib')
    img, (lo, hi) = stretch(tex)
    save_png(img, os.path.join(a.out, 'texture.png'))
    # the same geometry at output pixels, for the support map
    _G['src'], _G['nrm'] = zyx, n
    Hh, Ww = tex.shape
    P = np.empty((Hh, Ww, 3), np.float32)
    for c in range(0, Ww, 4096):
        Pt, _ = _grid_tile(0, Hh, c, min(c + 4096, Ww), f)
        P[:, c:c + Pt.shape[1]] = Pt
    valid = np.isfinite(P).all(-1)
    rec = dict(surface=os.path.abspath(a.surface), level=a.level, pixel_vox=pix, pixel_um=pix * a.voxel_um,
               shape=[Hh, Ww], surface_px=int(valid.sum()), sampled_px=int(np.isfinite(tex).sum()),
               unavailable_px=int((valid & ~np.isfinite(tex)).sum()), stretch=[lo, hi], orientation=orec,
               chunks=st, area_cm2_surface=float(valid.sum() * (pix * a.voxel_um * 1e-4) ** 2))
    if a.labels and os.path.exists(a.labels):
        # quilt: class of the nearest quilt cell (trace / fill / conflict), none beyond 1.5 concat steps
        from scipy.spatial import cKDTree
        L = np.load(a.labels)
        tree = cKDTree(L[:, :3])
        ok = np.isfinite(P).all(-1)
        lab = np.full(P.shape[:2], 0, np.uint8)
        pts = P[ok]
        res = np.zeros(len(pts), np.uint8)
        for b in range(0, len(pts), 1 << 23):
            d_, j_ = tree.query(pts[b:b + (1 << 23)], k=1, distance_upper_bound=a.label_radius, workers=-1)
            hit = np.isfinite(d_)
            rr = np.zeros(len(d_), np.uint8)
            rr[hit] = L[j_[hit], 3].astype(np.uint8)
            res[b:b + len(d_)] = rr
        lab[ok] = res
        # classes for window_pick: 0 trace, 1 fill, 2 conflict/none, 3 no surface
        cls = np.where(~valid, 3, np.where(lab == 1, 0, np.where(lab == 2, 1, 2))).astype(np.uint8)
        qlut = np.array([(40, 200, 90), (60, 120, 240), (200, 40, 40), (0, 0, 0)], np.uint8)
        rgb = qlut[cls]
        rgb[valid & (lab == 3)] = (230, 60, 200)
        save_png(rgb, os.path.join(a.out, 'support.png'))
        ov = (0.65 * np.repeat(img[..., None], 3, -1) + 0.35 * rgb).astype(np.uint8)
        ov[cls == 3] = 0
        save_png(ov, os.path.join(a.out, 'overlay.png'))
        tot = max(int((cls <= 2).sum()), 1)
        px_cm2 = (pix * a.voxel_um * 1e-4) ** 2
        rec['support'] = dict(mode='quilt labels', trace_frac=int((cls == 0).sum()) / tot, fill_frac=int((cls == 1).sum()) / tot,
                              conflict_frac=int((valid & (lab == 3)).sum()) / tot,
                              none_frac=int((valid & (lab == 0)).sum()) / tot,
                              trace_cm2=float((cls == 0).sum() * px_cm2), fill_cm2=float((cls == 1).sum() * px_cm2),
                              colours=dict(trace='green', fill='blue', conflict='magenta', none='red'))
        win = max(8, int(a.crop_px / pix))
        best, worst = window_pick(cls, win)
        rec['crops'] = []
        os.makedirs(os.path.join(a.out, 'crops'), exist_ok=True)
        for name, w in (('trace', best), ('fill', worst)):
            if w is None:
                rec['crops'].append(dict(name=name, found=False))
                continue
            fo, y, x, fp = w
            r0, c0 = int(y * pix), int(x * pix)
            crop, _, _ = render_grid(zyx, n, step / 1.0, [-1.0, 0.0, 1.0], a.volume.rstrip('/') + '/0', 'zyx',
                                     os.path.join(a.cache, 'L0') if a.cache else None, 1.0, 'mean', a.workers,
                                     tile=256, rows=(r0, r0 + a.crop_px), cols=(c0, c0 + a.crop_px))
            ci, _ = stretch(crop)
            save_png(ci, os.path.join(a.out, 'crops', f'{name}_L0.png'))
            sup = np.kron(rgb[y:y + win, x:x + win], np.ones((int(pix), int(pix), 1), np.uint8))[:ci.shape[0], :ci.shape[1]]
            save_png((0.7 * np.repeat(ci[..., None], 3, -1) + 0.3 * sup).astype(np.uint8),
                     os.path.join(a.out, 'crops', f'{name}_L0_overlay.png'))
            rec['crops'].append(dict(name=name, found=True, trace_share=fo, trace_or_fill_share=fp,
                                     level_px_yx=[y, x], level0_px_yx=[r0, c0], size_px=a.crop_px))
        fold_rgb = fold_strip(ov, a.fold_width); fold_rgb_src = ov
    elif a.quads and os.path.exists(a.quads):
        dist = support_distance(P, a.quads)
        cls = support_classes(dist, valid)
        tifffile.imwrite(os.path.join(a.out, 'support_dist.tif'), dist, compression='zlib')
        rgb = classes_rgb(cls)
        save_png(rgb, os.path.join(a.out, 'support.png'))
        ov = (0.65 * np.repeat(img[..., None], 3, -1) + 0.35 * rgb).astype(np.uint8)
        ov[cls == 3] = 0
        save_png(ov, os.path.join(a.out, 'overlay.png'))
        tot = max(int((cls <= 2).sum()), 1)
        rec['support'] = dict(on_frac=int((cls == 0).sum()) / tot, near_frac=int((cls == 1).sum()) / tot,
                              none_frac=int((cls == 2).sum()) / tot, on_vox=1.5, near_vox=8.0,
                              on_cm2=float((cls == 0).sum() * (pix * a.voxel_um * 1e-4) ** 2))
        # per-column-band summary (bad bands visible as runs of low on-share)
        cb = max(1, Ww // 400)
        colon = [(int(c), float(((cls[:, c:c + cb] == 0).sum()) / max(1, (cls[:, c:c + cb] <= 2).sum())))
                 for c in range(0, Ww, cb)]
        rec['support']['on_share_by_column_band'] = dict(band_px=cb, values=colon)
        win = max(8, int(a.crop_px / pix))
        best, worst = window_pick(cls, win)
        rec['crops'] = []
        os.makedirs(os.path.join(a.out, 'crops'), exist_ok=True)
        for name, w in (('on_sheet', best), ('off_sheet', worst)):
            if w is None:
                rec['crops'].append(dict(name=name, found=False))
                continue
            fo, y, x, fp = w
            # level-0 render of that window: rows/cols in level-L px -> level-0 px
            f0 = step / 1.0
            r0, c0 = int(y * pix), int(x * pix)
            _G['vol'] = None
            crop, _, st0 = render_grid(zyx, n, f0, [-1.0, 0.0, 1.0], a.volume.rstrip('/') + '/0', 'zyx',
                                       os.path.join(a.cache, 'L0') if a.cache else None, 1.0, 'mean', a.workers,
                                       tile=256, rows=(r0, r0 + a.crop_px), cols=(c0, c0 + a.crop_px))
            ci, _ = stretch(crop)
            save_png(ci, os.path.join(a.out, 'crops', f'{name}_L0.png'))
            sup = np.kron(rgb[y:y + win, x:x + win], np.ones((int(pix), int(pix), 1), np.uint8))[:ci.shape[0], :ci.shape[1]]
            save_png((0.7 * np.repeat(ci[..., None], 3, -1) + 0.3 * sup).astype(np.uint8),
                     os.path.join(a.out, 'crops', f'{name}_L0_overlay.png'))
            rec['crops'].append(dict(name=name, found=True, on_share=fo, patch_present_share=fp,
                                     level_px_yx=[y, x], level0_px_yx=[r0, c0], size_px=a.crop_px,
                                     centre_zyx=[float(v) for v in P[min(y + win // 2, Hh - 1), min(x + win // 2, Ww - 1)]],
                                     no_surface_or_unavailable_px=int((~np.isfinite(crop)).sum())))
        fold_rgb = fold_strip(ov, a.fold_width); fold_rgb_src = ov
    else:
        fold_rgb = fold_strip(np.repeat(img[..., None], 3, -1), a.fold_width); fold_rgb_src = None
    save_png(fold_rgb, os.path.join(a.out, 'overview.png'))
    # download-sized copies. JPEG allows at most 65,500 px per side: widen the fold (doubling) until the folded
    # height fits; a strip too tall even unfolded is halved in resolution first (recorded in picture.json)
    jw, jsc, jimg = jpeg_fold(img.shape[0], img.shape[1], a.fold_width)
    ov_src = fold_rgb_src if fold_rgb_src is not None else np.repeat(img[..., None], 3, -1)
    for arr, name, qual in ((img, 'texture_folded.jpg', 88), (ov_src, 'overlay_folded.jpg', 85)):
        if jsc > 1:
            arr = arr[::jsc, ::jsc]
        Image.fromarray(fold_strip(arr, jw)).save(os.path.join(a.out, name), quality=qual)
    rec['jpeg_fold'] = dict(fold_width_px=jw, downsample=jsc)
    small = Image.fromarray(fold_rgb)
    s = min(1.0, 4000.0 / max(small.size))
    small.resize((max(1, int(small.size[0] * s)), max(1, int(small.size[1] * s))), Image.LANCZOS).save(
        os.path.join(a.out, 'overview_small.jpg'), quality=90)
    rec['wall_s'] = round(time.time() - t0, 1)
    json.dump(rec, open(os.path.join(a.out, 'picture.json'), 'w'), indent=1)
    print(json.dumps({k: rec[k] for k in ('shape', 'pixel_um', 'surface_px', 'unavailable_px', 'wall_s')}), flush=True)


def _zband_rows(zyx, f, zband):
    m = np.isfinite(zyx[..., 0]) & (zyx[..., 0] >= zband[0]) & (zyx[..., 0] < zband[1])
    rows = np.nonzero(m.any(1))[0]
    if not len(rows):
        return None
    return int(max(rows[0] - 1, 0) * f), int(min(rows[-1] + 2, zyx.shape[0] - 1) * f) + 1


def cmd_inkzarr(a):
    t0 = time.time()
    os.makedirs(a.out, exist_ok=True)
    zyx, n, orec, meta, step = _common(a)
    f = step / a.step
    zband = [int(v) for v in a.zband.split(':')] if a.zband else None
    rows = _zband_rows(zyx, f, zband) if zband else None
    ink, _, st = render_grid(zyx, n, f, list(range(-a.half, a.half + 1)), a.volume, a.axes,
                             a.cache, 1.0 / 1.0, 'max', a.workers, rows=rows, zband=zband)
    tifffile.imwrite(os.path.join(a.out, 'ink_raw.tif'), ink.astype(np.float16), compression='zlib')
    v = ink[np.isfinite(ink)]
    p95 = float(np.percentile(v, 95)) if v.size else 0.0
    img = (np.clip(np.nan_to_num(ink, nan=0) / max(p95, 1e-6), 0, 1) * 255).astype(np.uint8)
    save_png(img, os.path.join(a.out, 'ink.png'))
    fold = fold_strip(img, a.fold_width)
    Image.fromarray(fold).save(os.path.join(a.out, 'ink_overview.jpg'), quality=90)
    rec = dict(surface=os.path.abspath(a.surface), volume_axes=a.axes, pixel_vox=a.step, zband=zband, rows=rows,
               shape=list(ink.shape), p95=p95, sampled_px=int(np.isfinite(ink).sum()), orientation=orec,
               chunks=st, wall_s=round(time.time() - t0, 1),
               convention='max over offsets -half..+half (level-0 vox) along the inward normal, /p95 (render_ink.py)')
    json.dump(rec, open(os.path.join(a.out, 'ink.json'), 'w'), indent=1)
    print(json.dumps({k: rec[k] for k in ('shape', 'p95', 'sampled_px', 'wall_s')}), flush=True)


def cmd_layers(a):
    t0 = time.time()
    os.makedirs(os.path.join(a.out, 'layers'), exist_ok=True)
    zyx, n, orec, meta, step = _common(a)
    f = step / 1.0
    zband = [int(v) for v in a.zband.split(':')]
    rows = _zband_rows(zyx, f, zband)
    if rows is None:
        raise SystemExit(f'no surface cells with z in {zband}')
    offs = [float(k - a.center) for k in range(a.nlayers)]
    Wf = int(np.floor((zyx.shape[1] - 1) * f)) + 1
    R = rows[1] - rows[0]
    ld = os.path.join(a.out, 'layers')
    lpaths = [os.path.join(ld, f'{k:02d}.tif') for k in range(a.nlayers)]
    mpath = os.path.join(a.out, 'mask.tif')
    for p_ in lpaths + [mpath]:   # create the uncompressed, memory-mappable files (sparse on disk)
        del_ = tifffile.memmap(p_, shape=(R, Wf), dtype=np.uint8)
        del_.flush()
        del del_
    _, _, st = render_grid(zyx, n, f, offs, a.volume.rstrip('/') + '/0', 'zyx',
                           os.path.join(a.cache, 'L0') if a.cache else None, 1.0, 'layers', a.workers,
                           tile=512, rows=rows, zband=zband, layer_paths=lpaths, mask_path=mpath)
    lay = [tifffile.memmap(p_, mode='r') for p_ in lpaths]
    mask = tifffile.memmap(mpath, mode='r')
    c0, c1 = 0, Wf
    npx = int(np.count_nonzero(mask))
    step_prev = max(1, Wf // 16384)
    save_png((np.asarray(mask[:, ::step_prev]) * 255).astype(np.uint8), os.path.join(a.out, 'mask_preview.png'))
    save_png(np.asarray(lay[a.center][:, ::step_prev]), os.path.join(a.out, 'layer_center_preview.png'))
    if a.ink_volume:
        ink = tifffile.memmap(os.path.join(a.out, 'ink_zarr_band.tif'), shape=(R, Wf), dtype=np.float32)
        ink[:] = np.nan
        for q0 in range(0, Wf, 65536):   # column blocks bound memory
            q1 = min(q0 + 65536, Wf)
            blk, _, _ = render_grid(zyx, n, f, [-2.0, -1.0, 0.0, 1.0, 2.0], a.ink_volume, a.ink_axes,
                                    os.path.join(a.cache, 'ink') if a.cache else None, 1.0, 'max', a.workers,
                                    tile=512, rows=rows, cols=(q0, q1), zband=zband)
            blk[np.asarray(mask[:, q0:q1]) == 0] = np.nan
            ink[:, q0:q1] = blk
        ink.flush()
        v = np.asarray(ink[:, ::step_prev])
        vv = v[np.isfinite(v)]
        p95 = float(np.percentile(vv, 95)) if vv.size else 1.0
        save_png((np.clip(np.nan_to_num(v) / max(p95, 1e-6), 0, 1) * 255).astype(np.uint8),
                 os.path.join(a.out, 'ink_zarr_band_preview.png'))
    rec = dict(surface=os.path.abspath(a.surface), zband=zband, rows=list(rows), cols=[c0, c1],
               shape=[int(a.nlayers), int(mask.shape[0]), c1 - c0], offsets=[offs[0], offs[-1]],
               convention='layer k at (k - center) level-0 voxels along the INWARD normal; uint8 = round(uint16/257)',
               masked_px=npx, orientation=orec, chunks=st, files='layers/NN.tif, mask.tif (uint8 0/1), ink_zarr_band.tif '
               '(uncompressed, memory-mappable); *_preview.png are column-subsampled views',
               area_cm2=float(npx * (a.voxel_um * 1e-4) ** 2), wall_s=round(time.time() - t0, 1))
    json.dump(rec, open(os.path.join(a.out, 'layers.json'), 'w'), indent=1)
    print(json.dumps({k: rec[k] for k in ('shape', 'masked_px', 'area_cm2', 'wall_s')}), flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    for name in ('picture', 'inkzarr', 'layers'):
        q = sp.add_parser(name)
        q.add_argument('--surface', required=True)
        q.add_argument('--volume', required=True, help='CT OME-zarr base URL/path (picture, layers) or ink array (inkzarr)')
        q.add_argument('--out', required=True)
        q.add_argument('--umbilicus', required=True)
        q.add_argument('--cache', default=None)
        q.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
        q.add_argument('--voxel-um', type=float, default=7.91)
        q.add_argument('--fold-width', type=int, default=8192)
        if name == 'picture':
            q.add_argument('--level', type=int, default=2)
            q.add_argument('--quads', default='')
            q.add_argument('--crop-px', type=int, default=2048)
            q.add_argument('--labels', default='', help='quilt labels_pts.npy: support map = trace / fill / conflict / none')
            q.add_argument('--label-radius', type=float, default=30.0)
        if name == 'inkzarr':
            q.add_argument('--axes', default='yxz')
            q.add_argument('--step', type=float, default=2.0)
            q.add_argument('--half', type=int, default=2)
            q.add_argument('--zband', default='')
        if name == 'layers':
            q.add_argument('--zband', required=True)
            q.add_argument('--nlayers', type=int, default=65)
            q.add_argument('--center', type=int, default=32)
            q.add_argument('--ink-volume', default='', help='also sample this 3-D ink array on the band pixels')
            q.add_argument('--ink-axes', default='yxz')
    a = p.parse_args(argv)
    {'picture': cmd_picture, 'inkzarr': cmd_inkzarr, 'layers': cmd_layers}[a.cmd](a)


if __name__ == '__main__':
    main()
