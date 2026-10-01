"""tifxyz surfaces: load, save, normals, inward orientation, area, and layer sampling.

tifxyz: a folder with meta.json and x.tif, y.tif, z.tif (float, level-0 voxels; -1 = invalid)
and an optional mask.tif (0 = invalid). Grid axes are (row, col). meta.json 'scale' is the
grid's sampling in cells per level-0 voxel along (col, row) [tifxyz convention], so one cell
spans 1/scale voxels.
"""
import json
import os

import numpy as np
import tifffile


def load_tifxyz(path):
    with open(os.path.join(path, 'meta.json')) as f:
        meta = json.load(f)
    x = tifffile.imread(os.path.join(path, 'x.tif')).astype(np.float32)
    y = tifffile.imread(os.path.join(path, 'y.tif')).astype(np.float32)
    z = tifffile.imread(os.path.join(path, 'z.tif')).astype(np.float32)
    valid = (x != -1) & (y != -1) & (z != -1) & np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    mp = os.path.join(path, 'mask.tif')
    if os.path.exists(mp):
        m = tifffile.imread(mp)
        if m.ndim == 3:
            m = m[..., 0]
        if m.shape == valid.shape:
            valid &= m != 0
    zyx = np.stack([z, y, x], -1)
    zyx[~valid] = np.nan
    return zyx, valid, meta


def save_tifxyz(path, zyx, meta):
    os.makedirs(path, exist_ok=True)
    v = np.isfinite(zyx).all(-1)
    for i, n in enumerate('zyx'):
        a = zyx[..., i].astype(np.float32).copy()
        a[~v] = -1
        tifffile.imwrite(os.path.join(path, f'{n}.tif'), a, compression='zlib')
    with open(os.path.join(path, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)


def trim_to_valid(zyx, pad=0):
    """numpy equivalent of cropping a tifxyz to its valid-cell bounding box."""
    v = np.isfinite(zyx).all(-1)
    if not v.any():
        return zyx, (0, 0)
    r = np.nonzero(v.any(1))[0]
    c = np.nonzero(v.any(0))[0]
    r0, r1 = max(r[0] - pad, 0), min(r[-1] + 1 + pad, v.shape[0])
    c0, c1 = max(c[0] - pad, 0), min(c[-1] + 1 + pad, v.shape[1])
    return zyx[r0:r1, c0:c1], (r0, c0)


def cell_area_vox2(zyx):
    """Per-cell area (level-0 voxel^2) of the quad grid; NaN where any corner is invalid.
    Shape (H-1, W-1). Area = half the norm of the cross product of the quad's diagonals."""
    a, b = zyx[:-1, :-1], zyx[:-1, 1:]
    c, d = zyx[1:, 1:], zyx[1:, :-1]
    cr = np.cross(c - a, d - b)
    return 0.5 * np.linalg.norm(cr, axis=-1)


def grid_normals(zyx):
    """Unit normals (z,y,x) from central differences on the grid (one-sided at edges and
    next to invalid cells). NaN where no tangent pair is available."""
    def diff(axis):
        f = np.roll(zyx, -1, axis) - zyx
        b = zyx - np.roll(zyx, 1, axis)
        sl_last = [slice(None)] * 3
        sl_last[axis] = -1
        f[tuple(sl_last)] = np.nan
        sl_first = [slice(None)] * 3
        sl_first[axis] = 0
        b[tuple(sl_first)] = np.nan
        d = np.where(np.isfinite(f) & np.isfinite(b), 0.5 * (f + b), np.where(np.isfinite(f), f, b))
        return d
    du = diff(1)   # along columns
    dv = diff(0)   # along rows
    n = np.cross(du, dv)
    nn = np.linalg.norm(n, axis=-1, keepdims=True)
    with np.errstate(invalid='ignore', divide='ignore'):
        n = n / nn
    n[~np.isfinite(n).all(-1) | (nn[..., 0] == 0)] = np.nan
    return n


def load_umbilicus(path):
    """Umbilicus control points -> (z array, (y,x) array), sorted by z."""
    with open(path) as f:
        u = json.load(f)
    pts = u['control_points'] if isinstance(u, dict) and 'control_points' in u else u
    if isinstance(pts, dict):
        raise ValueError(f'unrecognised umbilicus format in {path}')
    arr = np.array([[p['z'], p['y'], p['x']] if isinstance(p, dict) else p for p in pts], np.float64)
    arr = arr[np.argsort(arr[:, 0])]
    return arr[:, 0], arr[:, 1:]


def axis_yx(uz, uyx, z):
    return np.stack([np.interp(z, uz, uyx[:, 0]), np.interp(z, uz, uyx[:, 1])], -1)


def inward_sign_per_vertex(zyx, n, uz, uyx):
    """+1 where n points toward the scroll axis (radially inward), -1 outward, 0 unknown."""
    ax = axis_yx(uz, uyx, zyx[..., 0])
    to_axis = ax - zyx[..., 1:]
    d = np.einsum('...i,...i->...', n[..., 1:], to_axis)
    s = np.sign(d)
    s[~np.isfinite(d)] = 0
    return s


def orient_inward(zyx, n, uz, uyx, components=None):
    """Flip normals so they point inward. With `components` (int label grid, 0 = none), one
    flip per component by majority of per-vertex signs (a flattened component has a single
    handedness); returns (normals, report). Without components, per-vertex."""
    s = inward_sign_per_vertex(zyx, n, uz, uyx)
    rep = {}
    if components is None:
        out = n * np.where(s == 0, 1, s)[..., None]
        rep['disagree_frac'] = 0.0
        return out, rep
    out = n.copy()
    flips, dis = {}, 0
    tot = 0
    for lab in np.unique(components):
        if lab == 0:
            continue
        m = components == lab
        pos, neg = int((s[m] > 0).sum()), int((s[m] < 0).sum())
        flip = -1.0 if neg > pos else 1.0
        out[m] *= flip
        flips[int(lab)] = {'flip': flip < 0, 'inward_votes': pos, 'outward_votes': neg}
        dis += min(pos, neg)
        tot += pos + neg
    rep['components'] = flips
    rep['disagree_frac'] = dis / max(tot, 1)
    return out, rep


def sample_layers(vol, zyx, normals, offsets, scale=1.0, chunk_rows=64):
    """Sample `vol` (ZarrArray) at zyx + k*normal for each k in offsets (level-0 voxels).
    `scale` maps level-0 coordinates into vol's frame (0.25 for level 2).
    Returns float32 (len(offsets), H, W), NaN where unavailable."""
    H, W = zyx.shape[:2]
    out = np.full((len(offsets), H, W), np.nan, np.float32)
    for r0 in range(0, H, chunk_rows):
        p = zyx[r0:r0 + chunk_rows].reshape(-1, 3)
        nn = normals[r0:r0 + chunk_rows].reshape(-1, 3)
        ok = np.isfinite(p).all(1) & np.isfinite(nn).all(1)
        if not ok.any():
            continue
        for i, k in enumerate(offsets):
            q = (p[ok] + k * nn[ok]) * scale
            v = np.full(len(p), np.nan, np.float32)
            v[ok] = vol.sample(q)
            out[i, r0:r0 + chunk_rows] = v.reshape(-1, W)
    return out


def to_uint8(img, lo_pct=1.0, hi_pct=99.0, lo=None, hi=None):
    """Percentile-stretch to uint8; NaN (unavailable) -> 0 and reported separately."""
    v = img[np.isfinite(img)]
    if v.size == 0:
        return np.zeros(img.shape, np.uint8), (None, None)
    lo = np.percentile(v, lo_pct) if lo is None else lo
    hi = np.percentile(v, hi_pct) if hi is None else hi
    o = np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1) * 255
    o[~np.isfinite(img)] = 0
    return o.astype(np.uint8), (float(lo), float(hi))
