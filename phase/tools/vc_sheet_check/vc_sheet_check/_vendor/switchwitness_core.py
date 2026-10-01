"""Pipeline stages. Field code follows phase/x1/step3_field.py; pairs follow phase/x2/prep.py; the witness imports
phase/x2/common.py unmodified (its module-level slab/F are rebound here for the chosen slab and level)."""
import csv, io, json, re, sys, time, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, zarr
REPO = Path(__file__).resolve().parents[3]; sys.path[:0] = [str(REPO), str(REPO / "phase/scripts"), str(REPO / "phase/x2")]
T0 = time.time()
def _rss():
    try: return next(int(l.split()[1]) // 1024 for l in open("/proc/self/status") if l.startswith("VmRSS"))
    except Exception: return -1
def log(*a): print(f"[{time.time() - T0:7.1f}s {_rss()}MB]", *a, flush=True)

# ---------------- patches ----------------
BIN = np.dtype([("qx", "<f4"), ("qy", "<f4"), ("x", "<f4"), ("y", "<f4"), ("z", "<f4")])  # pipeline9/bin2csv.cpp:5
def _tif(b):
    """Uncompressed single-strip float32 TIFF fast path (as phase/x1/ingest.py); tifffile otherwise."""
    import struct
    bo = "<" if b[:2] == b"II" else ">"; off = struct.unpack(bo + "I", b[4:8])[0]; n = struct.unpack(bo + "H", b[off:off + 2])[0]; tg = {}
    for i in range(n):
        t, ty, c, v = struct.unpack(bo + "HHII", b[off + 2 + 12 * i:off + 14 + 12 * i]); tg[t] = v if ty == 4 else (v & 0xFFFF if bo == "<" else v >> 16)
    if tg.get(258) == 32 and tg.get(339) == 3 and tg.get(259, 1) == 1 and tg.get(278, tg[257]) >= tg[257]:
        w, h = tg[256], tg[257]; return np.frombuffer(b, bo + "f4", w * h, tg[273]).reshape(h, w).astype(np.float32)
    import tifffile; return tifffile.imread(io.BytesIO(b)).astype(np.float32)
_ZIPS = {}
def _zip(src):
    if src not in _ZIPS: _ZIPS[src] = zipfile.ZipFile(src)
    return _ZIPS[src]
def list_sources(paths):
    """Yield (id, source, member, kind). A source is a zip or directory of tifxyz patch_N/ folders or *.bin files."""
    for p in map(Path, paths):
        names = _zip(str(p)).namelist() if p.suffix == ".zip" else [str(q.relative_to(p)) for q in sorted(p.rglob("*")) if q.is_file()]
        items = []
        for n in names:
            m = re.search(r"(?:^|/)patch_(\d+)/x\.tif$", n)
            if m: items.append((int(m.group(1)), str(p), n[:-5], "tifxyz")); continue
            m = re.search(r"(\d+)\.bin$", n)
            if m: items.append((int(m.group(1)), str(p), n, "bin"))
        yield from sorted(items)
def read_patch(src, member, kind):
    """-> grid (h,w,3) float32 L0 xyz with NaN holes. tifxyz: -1 marks holes. bin: grid from quadmesh qx,qy."""
    rd = (lambda n: _zip(src).read(n)) if src.endswith(".zip") else (lambda n: open(Path(src) / n, "rb").read())
    if kind == "tifxyz":
        g = np.stack([_tif(rd(member + c + ".tif")) for c in "xyz"], -1); g[~((g[..., 0] > 0) & np.isfinite(g).all(-1))] = np.nan; return g
    a = np.frombuffer(rd(member), BIN); i = np.rint(a["qy"] - a["qy"].min()).astype(int); j = np.rint(a["qx"] - a["qx"].min()).astype(int)
    g = np.full((i.max() + 1, j.max() + 1, 3), np.nan, np.float32); g[i, j] = np.stack([a["x"], a["y"], a["z"]], 1); return g
def build_index(sources, labels, cache):
    f = cache / "index.csv"
    if f.exists(): return list(csv.DictReader(open(f)))
    rows = []
    for pid, src, mem, kind in list_sources(sources):
        g = read_patch(src, mem, kind); v = g[np.isfinite(g).all(-1)]
        if not len(v): continue
        lo, hi, c = v.min(0), v.max(0), v.mean(0)
        rows.append(dict(id=pid, label=labels.get(pid, "unknown"), source=src, member=mem, kind=kind, n=len(v),
                         xmin=lo[0], ymin=lo[1], zmin=lo[2], xmax=hi[0], ymax=hi[1], zmax=hi[2], cx=c[0], cy=c[1], cz=c[2]))
        if len(rows) % 5000 == 0: log("indexed", len(rows))
    with open(f, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return list(csv.DictReader(open(f)))

# ---------------- volume ----------------
class Volume:
    def __init__(s, path, level):
        s.base = f"{path.rstrip('/')}/{level}"; s.http = path.startswith("http"); s.level = level
        if s.http:
            s.meta = json.loads(urllib.request.urlopen(s.base + "/.zarray", timeout=60).read())
            from numcodecs import get_codec; s.codec = get_codec(s.meta["compressor"]) if s.meta["compressor"] else None
        else:
            s.arr = zarr.open_array(s.base, mode="r"); s.meta = dict(shape=list(s.arr.shape), chunks=list(s.arr.chunks), dtype=str(s.arr.dtype))
        s.shape, s.chunks, s.dtype = s.meta["shape"], s.meta["chunks"], np.dtype(s.meta["dtype"])
    def read(s, lo, hi):
        if not s.http: return np.asarray(s.arr[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]])
        out = np.zeros([b - a for a, b in zip(lo, hi)], s.dtype); C = s.chunks; sep = s.meta.get("dimension_separator", ".")
        keys = [(a, b, c) for a in range(lo[0] // C[0], (hi[0] - 1) // C[0] + 1) for b in range(lo[1] // C[1], (hi[1] - 1) // C[1] + 1) for c in range(lo[2] // C[2], (hi[2] - 1) // C[2] + 1)]
        def one(k):
            try: raw = urllib.request.urlopen(f"{s.base}/{sep.join(map(str, k))}", timeout=180).read()
            except urllib.error.HTTPError as e:
                if e.code == 404: return 0
                raise
            a = np.frombuffer(s.codec.decode(raw) if s.codec else raw, s.dtype).reshape(C)
            o = [k[d] * C[d] for d in range(3)]; src = tuple(slice(max(lo[d] - o[d], 0), min(hi[d] - o[d], C[d])) for d in range(3))
            dst = tuple(slice(max(o[d] - lo[d], 0), max(o[d] - lo[d], 0) + (src[d].stop - src[d].start)) for d in range(3)); out[dst] = a[src]; return len(raw)
        with ThreadPoolExecutor(16) as ex: n = sum(ex.map(one, keys))
        return out, dict(chunks=len(keys), bytes=int(n))

def to_slab(xyz, level, origin):     # L0 xyz -> slab zyx at level (voxel-centre convention)
    return (xyz[..., ::-1] + 0.5) / 2 ** level - 0.5 - origin

# ---------------- field (X1 step 3 settings) ----------------
def field(vol, rows, grids, zr, fdir, level, um0):
    from scipy import ndimage as ndi
    from scipy.ndimage import map_coordinates, gaussian_filter1d
    from skimage.filters import threshold_otsu
    from phase.core.monogenic import _block_monogenic, halo_for
    from phase.core._chunks import iter_cores, read_block
    import m2_support; from orient3d_standin import orient
    meta_f = fdir / "field.json"
    if meta_f.exists() and json.load(open(meta_f)).get("done"): return json.load(open(meta_f))
    fdir.mkdir(parents=True, exist_ok=True); zo = lambda n, sh, dt: zarr.open_array(str(fdir / n), mode="w", shape=sh, chunks=(128,) * 3 if len(sh) == 3 else (3, 128, 128, 128), dtype=dt)
    s = 2 ** level; pad = 16
    lo = [int((zr[0] + 0.5) / s - 0.5), int(min(float(r["ymin"]) for r in rows) / s) - pad, int(min(float(r["xmin"]) for r in rows) / s) - pad]
    hi = [int((zr[1] + 0.5) / s - 0.5), int(max(float(r["ymax"]) for r in rows) / s) + pad, int(max(float(r["xmax"]) for r in rows) / s) + pad]
    lo = [max(0, v) for v in lo]; hi = [min(v, S) for v, S in zip(hi, vol.shape)]
    res = dict(level=level, origin=lo, shape=[b - a for a, b in zip(lo, hi)], um_per_vox=um0 * s)
    if (fdir / "raw.zarr/.zarray").exists(): raw = zarr.open_array(str(fdir / "raw.zarr"), mode="r")[...]; res["pull"] = "cached"
    else:
        r_ = vol.read(lo, hi); raw, res["pull"] = r_ if isinstance(r_, tuple) else (r_, "local"); del r_; zo("raw.zarr", raw.shape, raw.dtype)[...] = raw
    log("slab", res["shape"], res["pull"]); SH = np.array(raw.shape); org = np.array(lo)
    # period: B4 autocorrelation along patch-grid normals (as X1)
    rng = np.random.default_rng(1667); prof = []; t = np.arange(-40, 40.01, 0.5)
    for k in rng.choice(len(grids), min(400, len(grids)), replace=False):
        g = grids[k]; nr = np.cross(np.gradient(g, axis=0), np.gradient(g, axis=1)); nr /= np.linalg.norm(nr, axis=-1, keepdims=True)
        cand = np.argwhere(np.isfinite(nr).all(-1))
        for i, j in cand[rng.choice(len(cand), min(10, len(cand)), replace=False)] if len(cand) else []:
            q = to_slab(g[i, j][None], level, org)[0][:, None] + nr[i, j][::-1][:, None] * t[None]
            if (q.min(1) >= 0).all() and (q.max(1) <= SH[:, None] - 1).all(): prof.append(map_coordinates(raw, q, order=1))
    prof = np.array(prof, float); d = prof - gaussian_filter1d(prof, 400 / res["um_per_vox"] / 0.5, axis=1); d = d[d.std(1) > 1e-6 * max(1.0, np.abs(prof).max())]
    ac = lambda x: (lambda f: (lambda a: a / a[0])(np.fft.irfft(f * np.conj(f))[:len(x)]))(np.fft.rfft(x - x.mean(), 2 * len(x)))
    m = np.mean([ac(x) for x in d], 0)[:80]; mn = np.where((m[1:-1] < m[:-2]) & (m[1:-1] < m[2:]))[0] + 1; st = mn[0]
    mx = np.where((m[st:-1] > m[st - 1:-2]) & (m[st:-1] > m[st + 1:]))[0] + st; k = mx[0]; y0, y1, y2 = m[k - 1:k + 2]
    per = float((k + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)) * 0.5); res.update(period_vox=per, period_um=per * res["um_per_vox"], n_profiles=len(d)); log("period", per, per * res["um_per_vox"])
    sub = raw[::2, ::4, ::4]; otsu = float(threshold_otsu(sub[sub > 0])); del sub
    fg = raw > otsu; env = np.empty_like(fg)
    for z in range(fg.shape[0]): env[z] = ndi.binary_fill_holes(ndi.binary_closing(fg[z], iterations=4))
    zo("envelope.zarr", env.shape, np.uint8)[...] = env; res.update(otsu=otsu, env_frac=float(env.mean())); log("stage")
    halo = halo_for(per); nb = 0
    if (fdir / "mono.done").exists():      # resumable: monogenic outputs complete from an earlier run
        amp = zarr.open_array(str(fdir / "amp.zarr"), mode="r")[...]; zp = zarr.open_array(str(fdir / "psi_unoriented.zarr"), mode="r")
        zn = zarr.open_array(str(fdir / "normal_unit.zarr"), mode="r"); res["monogenic"] = "resumed"; cores = []
    else:
        amp = np.zeros(raw.shape, np.float16); zp = zo("psi_unoriented.zarr", raw.shape, np.uint8); zn = zo("normal_unit.zarr", (3,) + raw.shape, np.int8); cores = list(iter_cores(raw.shape, 128))
    for core in cores:
        if not env[core].any(): continue
        x, inner = read_block(raw, core, halo); p, a, n, _ = _block_monogenic(x.astype(np.float32), per, 1.5, inner)
        zp[core] = np.round(p * 256).astype(np.uint8); amp[core] = a; zn[(slice(None),) + core] = np.round(n * 127).astype(np.int8); nb += 1
        if nb % 50 == 0: log("monogenic blocks", nb)
    del raw; res.update(halo=halo, blocks=nb)
    if cores: zo("amp.zarr", amp.shape, np.float16)[...] = amp; (fdir / "mono.done").touch()
    c = np.zeros((env.shape[0], 2), np.float32); yy, xx = np.arange(env.shape[1], dtype=float), np.arange(env.shape[2], dtype=float)
    for z in range(env.shape[0]):
        e = env[z]; w_ = max(e.sum(), 1); c[z] = (e.sum(1) @ yy / w_, e.sum(0) @ xx / w_)
    c = gaussian_filter1d(c, 20, axis=0).astype(np.float32); del env; log("stage")
    m2_support.BLK = int(round(per)); a_ = amp[fg]; nn = a_.size; h = (nn - 1) * 0.35; kk = int(np.floor(h)); a_.partition([kk, min(kk + 1, nn - 1)])
    tau = float(a_[kk]) + (h - kk) * (float(a_[min(kk + 1, nn - 1)]) - float(a_[kk])); del a_, fg
    bp = m2_support.block_p90(amp); B = m2_support.BLK; Y, X = amp.shape[1:]; sup = np.empty(amp.shape, bool); log("stage")
    for i in range(bp.shape[0]):
        thr = np.maximum(tau, 0.25 * np.repeat(np.repeat(bp[i], B, 0), B, 1)[:Y, :X]); sup[i * B:(i + 1) * B] = amp[i * B:(i + 1) * B] > thr[None]
    log("thresholds"); del amp; env = zarr.open_array(str(fdir / "envelope.zarr"), mode="r")[...].view(bool); sup &= env; log("env")
    # X3 deviation: no full-volume 26-connected label (OOM here); orient's largest_share is reported instead
    res["gate"] = dict(tau=tau, support_share_of_envelope=float(np.count_nonzero(sup) / max(np.count_nonzero(env), 1))); del env
    zs = zo("support.zarr", sup.shape, np.uint8); zs[...] = sup; del sup; log("gate", res["gate"])
    class Sc:
        def __init__(q, a, k): q.a, q.k, q.shape, q.ndim = a, k, a.shape, a.ndim
        def __getitem__(q, i): return np.asarray(q.a[i], np.float32) * q.k
    amp = zarr.open_array(str(fdir / "amp.zarr"), mode="r")[...]; info = {}
    orient(Sc(zn, 1 / 127), c, psi=Sc(zp, 1 / 256), out=str(fdir / "orient"), amp=amp, support=zs, info=info)
    res["orient"] = {k: v for k, v in info.items() if k in ("frustration", "largest_share", "components_after_mask", "masked_voxel_frac")}; res["done"] = True
    json.dump(res, open(meta_f, "w"), indent=1); log("orient", res["orient"]); return res

# ---------------- pairs (X2 prep.py rules) ----------------
def pairs(rows, grids, cache):
    f = cache / "pairs_pts.npz"
    if f.exists(): return dict(np.load(f))
    from scipy.spatial import cKDTree
    XYZ, UV = [], []
    for g in grids:
        ok = np.isfinite(g).all(-1); ij = np.argwhere(ok); XYZ.append(g[ok].astype(np.float32)); UV.append(ij * 4.0)
    TR = [cKDTree(x) for x in XYZ]; N = len(rows)
    bb = np.array([[float(r[k]) for k in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")] for r in rows])
    def interp(g, uv):
        c = uv / 4.0; i0 = np.floor(c).astype(int); fr = (c - i0).astype(np.float32); h, w = g.shape[:2]
        ok = (i0[:, 0] >= 0) & (i0[:, 1] >= 0) & (i0[:, 0] < h - 1) & (i0[:, 1] < w - 1); out = np.full((len(uv), 3), np.nan, np.float32)
        if ok.any():
            a, b, fa, fb = i0[ok, 0], i0[ok, 1], fr[ok, 0:1], fr[ok, 1:2]
            out[ok] = g[a, b] * (1 - fa) * (1 - fb) + g[a + 1, b] * fa * (1 - fb) + g[a, b + 1] * (1 - fa) * fb + g[a + 1, b + 1] * fa * fb
        return out
    PA, PB, PI, meta = [], [], [], []
    for i in range(N):
        js = np.arange(i + 1, N); js = js[((bb[i, :3] <= bb[js, 3:] + 2) & (bb[js, :3] <= bb[i, 3:] + 2)).all(1)]
        for j in js:
            d, k = TR[i].query(XYZ[j], distance_upper_bound=2.0); m = np.isfinite(d)
            if m.sum() < 10: continue
            A, B = UV[i][k[m]], UV[j][m]; ma, mb = A.mean(0), B.mean(0); U, S, Vt = np.linalg.svd((B - mb).T @ (A - ma)); R = (U @ Vt).T; t = ma - R @ mb
            pb = interp(grids[j].astype(np.float32), (UV[i] - t) @ R); mm = np.isfinite(pb).all(1)
            if mm.sum() < 20: continue
            PA.append(XYZ[i][mm]); PB.append(pb[mm]); PI.append(np.full(mm.sum(), len(meta), np.int32)); meta.append((i, j))
        if i % 1000 == 0: log("pairs from patch", i, "/", N, "pairs", len(meta))
    out = dict(PA=np.concatenate(PA), PB=np.concatenate(PB), PI=np.concatenate(PI), meta=np.array(meta, np.int32)); np.savez(f, **out); return out

# ---------------- witness (X2 snapped counter, imported) ----------------
def bind_field(fdir, fmeta):
    import common
    common.F = Path(fdir); lv, org = fmeta["level"], np.array(fmeta["origin"])
    common.slab = lambda xyz: to_slab(xyz, lv, org)
    return common.Field(raw=False), fmeta["period_vox"] * 2 ** lv      # period in L0 vox
def witness(P, fld, per0, cache):
    f = cache / "witness.npz"
    if f.exists(): return dict(np.load(f))
    PA, PB, PI = P["PA"], P["PB"], P["PI"]
    sep = np.abs(np.sum((PB - PA) * fld.normal((PA + PB) / 2), 1)); ia = np.where(sep > 1)[0]
    pa, pb = PA[ia], PB[ia]; sa, _ = fld.snap(pa, tmax=per0); sb, _ = fld.snap(pb, tmax=per0); ok = np.isfinite(sa).all(1) & np.isfinite(sb).all(1)
    cs = np.full(len(ia), np.nan); c_, o_ = fld.count(sa[ok], sb[ok]); cs[np.where(ok)[0][o_]] = np.rint(c_[o_])
    out = dict(ia=ia, cs=cs, pi=PI[ia], sep=sep[ia]); np.savez(f, **out); log("witness testable", float(np.isfinite(cs).mean())); return out

def verdicts(W, npair, abs_median=False):
    cs, pi = W["cs"], W["pi"]; o = np.argsort(pi, kind="stable"); cut = np.searchsorted(pi[o], np.arange(npair + 1))
    V = np.array(["coincident"] * npair, object); MED = np.full(npair, np.nan); AG = np.full(npair, np.nan); NT = np.zeros(npair, int)
    for q in range(npair):
        if cut[q + 1] == cut[q]: continue
        s = cs[o[cut[q]:cut[q + 1]]]; s = s[np.isfinite(s)]
        if abs_median: s = np.abs(s)
        NT[q] = len(s)
        if not len(s): V[q] = "untestable"; continue
        md = np.round(np.median(s)); ag = float((s == md).mean()); MED[q], AG[q] = md, ag
        V[q] = ("same-sheet" if md == 0 else "switch") if ag >= 0.8 else "ambiguous"
    return V, MED, AG, NT

# ---------------- cards ----------------
def card(raw, fmeta, A, B, fn, title="", patches=()):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from scipy.ndimage import map_coordinates
    lv, org = fmeta["level"], np.array(fmeta["origin"]); a, b = to_slab(A, lv, org), to_slab(B, lv, org)
    u = (b - a) / max(np.linalg.norm(b - a), 1e-6); t_ = np.array([1.0, 0, 0]) if abs(u[0]) < 0.9 else np.array([0, 1.0, 0])
    v = t_ - u * (t_ @ u); v /= np.linalg.norm(v); c0 = (a + b) / 2; mm = 1000 / fmeta["um_per_vox"]; g = np.linspace(-mm, mm, 256)
    Q = c0 + g[:, None, None] * v + g[None, :, None] * u; img = map_coordinates(raw, Q.reshape(-1, 3).T, order=1, mode="nearest").reshape(256, 256)
    fig, ax = plt.subplots(figsize=(4, 4)); ax.imshow(img, cmap="gray", extent=(-mm, mm, mm, -mm)); wv = np.cross(u, v)
    for X, col in patches:
        X = to_slab(X, lv, org) - c0; s = np.abs(X @ wv) < 1.5; ax.plot(X[s] @ u, X[s] @ v, ".", ms=1.2, color=col)
    for p in (a, b): ax.plot((p - c0) @ u, (p - c0) @ v, "o", ms=6, mfc="none", mec="#ffd400", mew=1.1)
    ax.plot([mm - 8 - mm / 2 * 2, mm - 8], [mm - 8, mm - 8], "w-", lw=3); ax.text(mm - 8 - mm / 2, mm - 14, "1 mm", color="w", ha="center", fontsize=8)
    ax.set_xlim(-mm, mm); ax.set_ylim(mm, -mm); ax.set_xticks([]); ax.set_yticks([])
    if title: ax.set_title(title, fontsize=7)
    fig.savefig(fn, dpi=80, bbox_inches="tight"); plt.close(fig)
