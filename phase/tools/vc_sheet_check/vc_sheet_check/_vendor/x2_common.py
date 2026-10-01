"""X2 shared code: X1 field/sampler (copied from phase/x1/witness.py), snapped counter, CT-peak counter."""
import csv
from pathlib import Path
import numpy as np, zarr
from scipy.spatial import cKDTree
from scipy.signal import find_peaks
REPO = Path(__file__).resolve().parents[2]; F = REPO / "data/x1/field"; D2 = REPO / "data/x2"
Z0L0, Z1L0 = 2712, 3480; ORIGIN = np.array([1356, 0, 128])
SP = 2 * 8.493400333781194                     # measured spacing, L0 voxels (X1 step 3) = 134.4 um
UM0 = 7.91
def slab(xyz): return (xyz[..., ::-1] - 0.5) / 2 - ORIGIN
class Field:
    def __init__(s, raw=False):
        s.psi = zarr.open_array(str(F / "orient/psi_signed"), mode="r")[...]
        s.big = zarr.open_array(str(F / "orient/largest_oriented"), mode="r")[...] > 0
        s.nrm = zarr.open_array(str(F / "normal_unit.zarr"), mode="r")[...]
        s.raw = zarr.open_array(str(F / "raw.zarr"), mode="r")[...] if raw else None
        s.SH = np.array(s.psi.shape); s.CL = np.cos(2 * np.pi * np.arange(256) / 256); s.SL = np.sin(2 * np.pi * np.arange(256) / 256)
    def normal(s, p0):   # L0 xyz -> unit field normal (xyz), unoriented
        q = np.clip(np.rint(slab(p0)).astype(int), 0, s.SH - 1)
        n = s.nrm[:, q[..., 0], q[..., 1], q[..., 2]].astype(np.float32); n = np.moveaxis(n, 0, -1)[..., ::-1]
        return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    def sample(s, q):    # q (...,3) slab coords -> (phase turns, in-support, in-bounds)
        inb = ((q >= 0) & (q <= s.SH - 1)).all(-1); qn = np.clip(np.rint(q).astype(int), 0, s.SH - 1)
        ins = inb & s.big[qn[..., 0], qn[..., 1], qn[..., 2]]
        i0 = np.clip(np.floor(q).astype(int), 0, s.SH - 2); f = np.clip(q - i0, 0, 1); re = np.zeros(q.shape[:-1]); im = np.zeros(q.shape[:-1])
        for dz in (0, 1):
            for dy in (0, 1):
                for dx in (0, 1):
                    w = (f[..., 0] if dz else 1 - f[..., 0]) * (f[..., 1] if dy else 1 - f[..., 1]) * (f[..., 2] if dx else 1 - f[..., 2])
                    v = s.psi[i0[..., 0] + dz, i0[..., 1] + dy, i0[..., 2] + dx]; re += w * s.CL[v]; im += w * s.SL[v]
        return np.arctan2(im, re) / (2 * np.pi), ins, inb
    def ct(s, q):        # trilinear raw CT at slab coords
        from scipy.ndimage import map_coordinates
        return map_coordinates(s.raw, q.reshape(-1, 3).T, order=1, mode="nearest").reshape(q.shape[:-1])
    def count(s, pa, pb):  # X1 counter: integrated wrapped phase along pa->pb (L0 xyz), all samples in support
        a, b = slab(pa), slab(pb); L = np.linalg.norm(b - a, axis=1); C = np.full(len(a), np.nan); ok = np.zeros(len(a), bool); o = np.argsort(L)
        for k in range(0, len(a), 4000):
            i = o[k:k + 4000]; ns = int(np.ceil(L[i].max() / 0.5)) + 2; tt = np.linspace(0, 1, ns)
            ph, ins, _ = s.sample(a[i, None] + (b[i] - a[i])[:, None] * tt[None, :, None])
            d = np.diff(ph, axis=1); C[i] = ((d + 0.5) % 1.0 - 0.5).sum(1); ok[i] = ins.all(1)
        return C, ok
    def snap(s, p, tmax=SP, step=0.5):
        """Move each L0 point along the field normal to the nearest psi=0 crossing (|t| <= tmax L0 vox; the phase
        travelled is <= 0.5 turn by construction since psi(p) is wrapped to [-.5,.5)). Samples up to the crossing must
        be in support. Returns snapped points (nan if none) and t."""
        n = s.normal(p); t = np.arange(0, tmax + 1e-6, step); out = np.full(p.shape, np.nan); tb = np.full(len(p), np.nan)
        for k in range(0, len(p), 20000):
            sl = slice(k, k + 20000); best = np.full(len(p[sl]), np.inf); bt = np.full(len(p[sl]), np.nan)
            for sg in (1, -1):
                q = slab(p[sl, None] + sg * n[sl, None] * t[None, :, None]); ph, ins, _ = s.sample(q)
                d = np.diff(ph, axis=1); d = (d + 0.5) % 1.0 - 0.5; phi = ph[:, :1] + np.concatenate([np.zeros((len(ph), 1)), np.cumsum(d, 1)], 1)
                cr = (np.sign(phi[:, :-1]) != np.sign(phi[:, 1:])) | (phi[:, :-1] == 0)
                okc = cr & np.cumprod(ins[:, 1:] & ins[:, :-1], 1).astype(bool) & ins[:, :1]
                has = okc.any(1); j = np.argmax(okc, 1)
                fr = np.where(has, phi[np.arange(len(j)), j] / np.where(has, phi[np.arange(len(j)), j] - phi[np.arange(len(j)), j + 1], 1), 0)
                tc = (t[j] + np.clip(fr, 0, 1) * step) * sg
                better = has & (np.abs(tc) < best); best[better] = np.abs(tc[better]); bt[better] = tc[better]
            tb[sl] = bt; m = np.isfinite(bt); o = out[sl]; o[m] = p[sl][m] + n[sl][m] * bt[m, None]; out[sl] = o
        return out, tb
    def peaks(s, pa, pb, prom, ext=0.25 * SP, step=0.5):
        """Model-free counter: prominent CT maxima along pa->pb extended by ext at both ends, minus 1 (unsigned)."""
        a, b = slab(pa), slab(pb); u = b - a; L = np.linalg.norm(u, axis=1); u = u / np.maximum(L[:, None], 1e-9)
        e = ext / 2; out = np.full(len(a), np.nan); ok = np.zeros(len(a), bool); o = np.argsort(L)
        for k in range(0, len(a), 4000):
            i = o[k:k + 4000]; ns = int(np.ceil((L[i].max() + 2 * e) / step)) + 1; tt = -e + step * np.arange(ns)
            q = a[i, None] + u[i, None] * tt[None, :, None]; nr = np.floor((L[i] + 2 * e) / step).astype(int) + 1
            inb = ((q >= 0) & (q <= s.SH - 1)).all(-1) | (np.arange(ns)[None] >= nr[:, None]); v = s.ct(q)
            for r, ii in enumerate(i):
                if not inb[r].all(): continue
                pk, _ = find_peaks(v[r, :nr[r]], prominence=prom); out[ii] = max(len(pk) - 1, 0); ok[ii] = True
        return out, ok

def load_patches():
    rows = [r for r in csv.DictReader(open(REPO / "phase/x1/patches.csv")) if Z0L0 <= float(r["cz"]) < Z1L0]
    P = np.memmap(REPO / "data/x1/points.f32", np.float32, "r").reshape(-1, 3); IJ = np.memmap(REPO / "data/x1/points_ij.u8", np.uint8, "r").reshape(-1, 2)
    G, UV, XYZ = [], [], []
    for r in rows:
        o, n = int(r["offset"]), int(r["n"]); xyz = np.asarray(P[o:o + n], np.float32); ij = np.asarray(IJ[o:o + n]).astype(int)
        g = np.full((int(r["h"]), int(r["w"]), 3), np.nan, np.float32); g[ij[:, 0], ij[:, 1]] = xyz; G.append(g); UV.append(ij * 4.0); XYZ.append(xyz)
    return rows, G, UV, XYZ
