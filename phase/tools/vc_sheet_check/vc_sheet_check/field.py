"""Fixed-period phase field on the mesh's bounding box plus a halo.

This is phase/s1b/build_field_fixed.py's build() with two changes, both
recorded in the README:
  1. the box is the mesh bbox plus a halo (it was a hand-picked ROI);
  2. the period is fixed at 80 um for every scroll (S1b used 77.34 um reused /
     87 um built); it is never estimated.
Everything else (Otsu envelope, log-Gabor monogenic at bandwidth 1.5 octaves,
M2 amplitude gate at the 35th percentile and 0.25 x local p90, the 3-D
orientation stand-in) is the frozen code, vendored unmodified in _vendor/.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

# Contract parameters (SessA-3): period = the training field's, phase/x3/results/slab2/field.json period_um;
# halo 380 um. SessA used 80 um as the period, a misreading of the brief (the 80 um was the halo; CONTRACT A5.2).
PERIOD_UM = 118.66950981993529
HALO_UM = 380.0


def _log(*a):
    print(f"[field {time.strftime('%H:%M:%S')}]", *a, flush=True)


def halo_voxels(halo_um, um0=7.91):
    """Halo in L0 voxels from a length in um (rounded up). Period and halo are separate parameters."""
    return int(round(halo_um / um0))      # A7.1: 380 um = 48 voxels (round to nearest)


class AxisFile:
    """axis_xy(z) -> (x, y), L0 voxels, linear in z and clamped beyond the control points (contract_io.axis_yx_at).
    Counts the queries outside the control points' z range (`outside`), which a run reports as axis_queries_outside
    (A12.1: ours clamps there, villa extrapolates)."""
    def __init__(self, z, y, x, fmt, path):
        self.z, self.y, self.x, self.format, self.path = np.asarray(z, float), np.asarray(y, float), np.asarray(x, float), fmt, str(path)
        self.outside = 0; self.queries = 0

    def __call__(self, z):
        zq = np.asarray(z, np.float64)
        self.queries += int(zq.size); self.outside += int(((zq < self.z[0]) | (zq > self.z[-1])).sum())
        return np.interp(zq, self.z, self.x), np.interp(zq, self.z, self.y)

    def report(self):
        return dict(path=self.path, format=self.format, control_points=int(len(self.z)), z_range=[float(self.z[0]), float(self.z[-1])],
                    axis_queries=self.queries, axis_queries_outside=self.outside)


def load_axis_file(path):
    """Axis file in any accepted format -> AxisFile (callable z -> (x, y)).
    A12.1 formats, read by integrator's contract_io.read_axis_file (coordinate_scale != 1 refused):
      - our CSV with a `z,y,x` header (phase/tools/axis/*.csv);
      - villa's umbilicus.json {"control_points": [{"z", "y", "x"}, ...]}.
    Also accepted (SessA's own writers, `--axis x6` and SessA-12): headerless 'z, y, x' lines (villa's umbilicus-*_zyx.txt layout)."""
    import sys
    path = Path(path)
    tools = str(Path(__file__).resolve().parents[2])                  # phase/tools (contract_io)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import contract_io as CIO
    if path.suffix.lower() == ".json":
        z, y, x = CIO.read_axis_file(path); return AxisFile(z, y, x, "umbilicus.json (A12.1)", path)
    first = next((ln for ln in open(path) if ln.strip()), "")
    if any(c.isalpha() for c in first):
        z, y, x = CIO.read_axis_file(path); return AxisFile(z, y, x, "csv z,y,x (A12.1)", path)
    P = np.loadtxt(path, delimiter=",", ndmin=2)
    P = P[np.argsort(P[:, 0], kind="stable")]
    return AxisFile(P[:, 0], P[:, 1], P[:, 2], "headerless z, y, x", path)


def box_for_mesh(lo_xyz, hi_xyz, halo_l0, level, vol_shape_zyx_l0):
    """L0 xyz bbox -> field box at `level` (zyx origin/shape), clipped to the volume."""
    s = 2 ** level
    lo = np.floor((np.asarray(lo_xyz)[::-1] - halo_l0) / s).astype(int)
    hi = np.ceil((np.asarray(hi_xyz)[::-1] + halo_l0 + 1) / s).astype(int)
    lim = np.ceil(np.asarray(vol_shape_zyx_l0) / s).astype(int)
    lo = np.maximum(lo, 0); hi = np.minimum(hi, lim)
    return lo.tolist(), hi.tolist()


def build(vol, level, um0, lo, hi, fdir, period_um=PERIOD_UM, axis_xy=None, axis_tag=None, keep_diag=False, gate=None):
    """vol: _vendor.switchwitness_core.Volume at `level`. lo/hi: zyx at `level`.
    axis_xy: optional scroll axis, L0 z -> (x, y) L0 (refmesh.build_axis). The orientation step signs each
    component so its normals point away from c(z). S1b used the box's own envelope centroid as c(z); in a
    sub-box that is not the scroll axis, and the crossing count's sign can come out flipped (measured on
    fixture region A: committed vs recomputed median_count correlation -0.92). Given an axis, c(z) is the
    axis, so +1 means outward as in the training field.
    gate: optional region gate from region_gate() (tiled fields, SessA-6): the box's Otsu threshold, envelope and support
    amplitude floor tau are then the region's, not the box's own, so every tile applies the same support rule."""
    import zarr
    from scipy import ndimage as ndi
    from scipy.ndimage import gaussian_filter1d
    from skimage.filters import threshold_otsu
    from ._vendor.core.monogenic import _block_monogenic, halo_for
    from ._vendor.core._chunks import iter_cores, read_block
    from ._vendor import m2_support
    from ._vendor.orient3d_standin import orient

    fdir = Path(fdir); fdir.mkdir(parents=True, exist_ok=True)
    meta_f = fdir / "field.json"
    if meta_f.exists():
        m = json.loads(meta_f.read_text())
        if m.get("done") and m["origin"] == list(lo) and m["shape"] == [b - a for a, b in zip(lo, hi)] \
                and m["period_um"] == period_um and m.get("axis_tag") == axis_tag \
                and (axis_xy is None) == (m.get("orientation_centre", "").startswith("box")) and (not keep_diag or m.get("keep_diag")) \
                and m.get("gate_tag") == (gate or {}).get("tag"):
            _log("reusing", fdir)
            return m

    def zo(n, sh, dt):
        return zarr.open_array(str(fdir / n), mode="w", shape=sh,
                               chunks=(128,) * 3 if len(sh) == 3 else (3, 128, 128, 128), dtype=dt)

    s = 2 ** level
    per = period_um / (um0 * s)
    res = dict(level=level, origin=list(lo), shape=[b - a for a, b in zip(lo, hi)], um_per_vox=um0 * s,
               period_vox=per, period_um=period_um, period_source="fixed, not estimated")
    t0 = time.time()
    r_ = vol.read(lo, hi)
    raw, res["pull"] = r_ if isinstance(r_, tuple) else (r_, "local"); del r_
    res["t_read_s"] = round(time.time() - t0, 1)
    _log("read", res["shape"], res["pull"], res["t_read_s"], "s")
    if not (raw > 0).any():
        raise RuntimeError("box has no nonzero CT (all chunks missing?)")
    res["missing_frac"] = float((raw == 0).mean())

    if gate is None:
        sub = raw[::2, ::4, ::4]
        otsu = float(threshold_otsu(sub[sub > 0])) if (sub > 0).sum() > 16 else float(np.percentile(raw, 90))
        del sub
        fg = raw > otsu; env = np.empty_like(fg)
        for z in range(fg.shape[0]):
            env[z] = ndi.binary_fill_holes(ndi.binary_closing(fg[z], iterations=4))
    else:
        otsu = float(gate["otsu"]); fg = raw > otsu
        env = _gate_envelope(gate, lo, hi, level)
        res["gate_tag"] = gate["tag"]
    res.update(otsu=otsu, env_frac=float(env.mean()))
    if keep_diag:          # SessA-2 exclusion diagnostics: keep the envelope
        zo("envelope.zarr", env.shape, np.uint8)[...] = env

    halo = halo_for(per)
    amp = np.zeros(raw.shape, np.float16)
    zp = zo("psi_unoriented.zarr", raw.shape, np.uint8)
    zn = zo("normal_unit.zarr", (3,) + raw.shape, np.int8)
    nb = 0; t0 = time.time()
    for core in iter_cores(raw.shape, 128):
        if not env[core].any():
            continue
        x, inner = read_block(raw, core, halo)
        p, a, n, _ = _block_monogenic(x.astype(np.float32), per, 1.5, inner)
        zp[core] = np.round(p * 256).astype(np.uint8); amp[core] = a
        zn[(slice(None),) + core] = np.round(n * 127).astype(np.int8); nb += 1
    del raw
    res.update(halo=int(halo), blocks=nb, t_monogenic_s=round(time.time() - t0, 1))
    _log("monogenic", nb, "blocks", res["t_monogenic_s"], "s")

    c = np.zeros((env.shape[0], 2), np.float32)
    yy, xx = np.arange(env.shape[1], dtype=float), np.arange(env.shape[2], dtype=float)
    for z in range(env.shape[0]):
        e = env[z]; w_ = max(e.sum(), 1); c[z] = (e.sum(1) @ yy / w_, e.sum(0) @ xx / w_)
    c = gaussian_filter1d(c, 20, axis=0).astype(np.float32)
    res["orientation_centre"] = "box envelope centroid (S1b)"
    if axis_xy is not None:
        zl0 = (np.arange(env.shape[0]) + lo[0] + 0.5) * s - 0.5
        axx, axy = axis_xy(zl0)
        c = np.stack([(np.asarray(axy) + 0.5) / s - 0.5 - lo[1], (np.asarray(axx) + 0.5) / s - 0.5 - lo[2]], 1).astype(np.float32)
        res["orientation_centre"] = "scroll axis" + (f" ({axis_tag})" if axis_tag else "")
    res["axis_tag"] = axis_tag

    m2_support.BLK = int(round(per)); a_ = amp[fg]; nn = a_.size
    if nn == 0:
        raise RuntimeError("no foreground voxels in box")
    tau = _p35(a_) if gate is None else float(gate["tau"]); del a_, fg
    bp = m2_support.block_p90(amp); B = m2_support.BLK; Y, X = amp.shape[1:]
    sup = np.empty(amp.shape, bool)
    for i in range(bp.shape[0]):
        thr = np.maximum(tau, 0.25 * np.repeat(np.repeat(bp[i], B, 0), B, 1)[:Y, :X])
        sup[i * B:(i + 1) * B] = amp[i * B:(i + 1) * B] > thr[None]
    sup &= env
    res["gate"] = dict(tau=tau, support_share_of_envelope=float(np.count_nonzero(sup) / max(np.count_nonzero(env), 1)))
    del env
    zs = zo("support.zarr", sup.shape, np.uint8); zs[...] = sup; del sup

    class Sc:
        def __init__(q, a, k): q.a, q.k, q.shape, q.ndim = a, k, a.shape, a.ndim
        def __getitem__(q, i): return np.asarray(q.a[i], np.float32) * q.k

    info = {}; t0 = time.time()
    orient(Sc(zn, 1 / 127), c, psi=Sc(zp, 1 / 256), out=str(fdir / "orient"), amp=amp,
           support=zs, info=info)
    del amp
    res["orient"] = {k: v for k, v in info.items()
                     if k in ("frustration", "largest_share", "components_after_mask", "masked_voxel_frac")}
    res["t_orient_s"] = round(time.time() - t0, 1)
    # working-state arrays the check never reads (T1's cleanup rule)
    import shutil
    for n in (("psi_unoriented.zarr", "orient/normal_oriented") if keep_diag else
              ("psi_unoriented.zarr", "support.zarr", "orient/normal_oriented", "orient/oriented_support")):
        shutil.rmtree(fdir / n, ignore_errors=True)
    res["keep_diag"] = bool(keep_diag)
    res["done"] = True
    meta_f.write_text(json.dumps(res, indent=1, default=float))
    _log("orient", res["orient"], res["t_orient_s"], "s")
    return res


def _p35(a_):
    """35th percentile, linear interpolation, by partition (the box gate's tau)."""
    nn = a_.size
    h = (nn - 1) * 0.35; kk = int(np.floor(h)); a_.partition([kk, min(kk + 1, nn - 1)])
    return float(a_[kk]) + (h - kk) * (float(a_[min(kk + 1, nn - 1)]) - float(a_[kk]))


def _gate_envelope(gate, lo, hi, level):
    """The region envelope (computed at gate['level']) resampled nearest to this box at `level`; outside it: False."""
    E = np.load(gate["env_path"], mmap_mode="r"); o = np.asarray(gate["env_origin"]); f = 2 ** (gate["level"] - level)
    idx = [(np.arange(a, b) // f) - oo for a, b, oo in zip(lo, hi, o)]
    ok = [(i >= 0) & (i < n) for i, n in zip(idx, E.shape)]
    out = np.zeros([b - a for a, b in zip(lo, hi)], bool)
    cl = [np.clip(i, 0, n - 1) for i, n in zip(idx, E.shape)]
    sub = np.asarray(E[cl[0].min():cl[0].max() + 1, cl[1].min():cl[1].max() + 1, cl[2].min():cl[2].max() + 1])
    sub = sub[np.ix_(*[c - c.min() for c in cl])]
    out[...] = sub & ok[0][:, None, None] & ok[1][None, :, None] & ok[2][None, None, :]
    return out


def region_gate(ct_spec, lo_l0, hi_l0, period_um, out_dir, level=1, n_blocks=16, seed=0, zstep=128, log=_log, keep_raw=False):
    """One support rule for all tiles of a region (SessA-6). lo/hi: region box in L0 z,y,x (include the halo).
    The box gate's statistics, over the region at the field level: otsu = Otsu of the region's nonzero CT subsample
    [::2, ::4, ::4]; envelope = per-z-slice binary closing (4 iterations) + hole filling of CT > otsu over whole region
    slices; tau = the 35th percentile of monogenic amplitude over foreground voxels of n_blocks 128^3 blocks drawn
    (default_rng(seed)) at envelope voxels. The region CT is cached once at `level` (read in z slabs of zstep)."""
    from scipy import ndimage as ndi
    from skimage.filters import threshold_otsu
    from . import sources as SRC
    from ._vendor.core.monogenic import _block_monogenic, halo_for
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    s1 = 2 ** level
    lo = [a // s1 for a in lo_l0]; hi = [-(-b // s1) for b in hi_l0]; sh = [b - a for a, b in zip(lo, hi)]
    ct = SRC.CT(ct_spec, level)
    rawp = out_dir / "region_raw.npy"
    raw = np.lib.format.open_memmap(rawp, mode="w+", dtype=np.uint16, shape=tuple(sh))
    subs, pulled = [], 0
    for z0 in range(0, sh[0], zstep):
        z1 = min(z0 + zstep, sh[0])
        r_ = ct.read([lo[0] + z0, lo[1], lo[2]], [lo[0] + z1, hi[1], hi[2]])
        a = r_[0] if isinstance(r_, tuple) else r_
        raw[z0:z1] = a; sb = a[(-z0) % 2::2, ::4, ::4]; subs.append(sb[sb > 0])
    raw.flush()
    sub = np.concatenate(subs); del subs
    otsu = float(threshold_otsu(sub)) if sub.size > 16 else float(np.percentile(raw, 90)); del sub
    envp = out_dir / "region_envelope.npy"
    env = np.lib.format.open_memmap(envp, mode="w+", dtype=bool, shape=tuple(sh))
    for z in range(sh[0]):
        env[z] = ndi.binary_fill_holes(ndi.binary_closing(raw[z] > otsu, iterations=4))
    env.flush()
    per = period_um / (7.91 * s1); halo = halo_for(per); rng = np.random.default_rng(seed)
    cand = np.argwhere(env[::8, ::8, ::8]) * 8
    pick = cand[rng.choice(len(cand), min(n_blocks, len(cand)), replace=False)]
    amps = []
    for c in pick:
        b0 = np.clip(c - 64 - halo, 0, None); b1 = np.minimum(c + 64 + halo, sh)
        x = np.asarray(raw[b0[0]:b1[0], b0[1]:b1[1], b0[2]:b1[2]], np.float32)
        inner = tuple(slice(int(cc - 64 - bb), int(cc + 64 - bb)) for cc, bb in zip(np.clip(c, 64, np.array(sh) - 64), b0))
        _, a, _, _ = _block_monogenic(x, per, 1.5, inner)
        amps.append(np.asarray(a, np.float32)[x[inner] > otsu])
    a_ = np.concatenate(amps) if amps else np.zeros(0, np.float32)
    tau = _p35(a_) if a_.size else float("nan")
    g = dict(otsu=otsu, tau=tau, env_path=str(envp), env_origin=lo, level=level, env_frac=float(np.mean(env[::4, ::4, ::4])),
             n_blocks=len(pick), n_fg_voxels=int(a_.size), region_l1_origin=lo, region_l1_shape=sh)
    g["tag"] = "region gate otsu=%.1f tau=%.1f level=%d" % (otsu, tau, level)
    log("region gate", {k: v for k, v in g.items() if k != "env_path"})
    json.dump(g, open(out_dir / "region_gate.json", "w"), indent=1)
    del raw
    if keep_raw:                      # SessA-12: tiles inside this box read their CT from this cache (identical voxels)
        g["raw_path"] = str(rawp); g["raw_origin"] = lo
    else:
        rawp.unlink(missing_ok=True)
    return g


class LocalCT:
    """A level-`level` CT box cached by region_gate(keep_raw=True); read(lo, hi) as sources.CT.read, for boxes inside it."""
    def __init__(self, raw_path, origin):
        self.a = np.load(raw_path, mmap_mode="r"); self.o = np.asarray(origin)

    def read(self, lo, hi):
        a0 = np.asarray(lo) - self.o; a1 = np.asarray(hi) - self.o
        if (a0 < 0).any() or (a1 > np.array(self.a.shape)).any():
            raise ValueError(f"box {lo}-{hi} outside the cached CT {self.o.tolist()} + {list(self.a.shape)}")
        return np.array(self.a[a0[0]:a1[0], a0[1]:a1[1], a0[2]:a1[2]]), {"local_cache": True}
