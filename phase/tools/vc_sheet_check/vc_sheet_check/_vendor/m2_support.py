#!/usr/bin/env python3
"""M2 steps 1-2: 3D amplitude gate (as M1c), gap-thickness check, support connectivity.

python3 phase/scripts/m2_support.py      (needs data/1667/m2/mono from m2_monogenic.py)
Outputs (gitignored): data/1667/m2/support.zarr (uint8), largest.zarr (uint8), envelope.zarr (uint8).
Compact results: phase/data_small/m2_support.json, m2_gap_thickness.csv.
"""
import csv, json, resource, sys, time
from pathlib import Path
import numpy as np, zarr
from scipy import ndimage as ndi
from skimage.filters import threshold_otsu

REPO = Path(__file__).resolve().parents[2]
M2 = REPO / "data/1667/m2"; OUT = REPO / "phase/data_small"
P = 9.0; BLK = 9                     # local-p90 block = 1 period; 3x3x3 blocks ~ 27 px window
SMOOTH_SIGMA = P / 2.3548            # Gaussian with FWHM = one period


def save(name, a):
    z = zarr.open_array(str(M2 / name), mode="w", shape=a.shape, chunks=(128, 128, 128), dtype=a.dtype, zarr_format=2)
    z[...] = a


def block_p90(amp):
    """p90 of each 9^3 block, then p90 over the 3x3x3 block neighbourhood (~27^3 window)."""
    Z, Y, X = amp.shape
    nb = [int(np.ceil(v / BLK)) for v in amp.shape]
    bp = np.empty(nb, np.float32)
    for i in range(nb[0]):
        sl = amp[i * BLK:(i + 1) * BLK]
        pad = [(0, BLK - sl.shape[0]), (0, nb[1] * BLK - Y), (0, nb[2] * BLK - X)]
        v = np.pad(sl, pad, mode="edge").reshape(BLK, nb[1], BLK, nb[2], BLK).transpose(1, 3, 0, 2, 4).reshape(nb[1], nb[2], -1)
        bp[i] = np.percentile(v, 90, axis=-1)
    return ndi.percentile_filter(bp, 90, size=3, mode="nearest")


def gate(amp, fg):
    """Support = amp > max(tau_abs, 0.25 x local p90); evaluated per 9-slice block (no full-size temporaries)."""
    tau = float(np.percentile(amp[fg], 35))
    bp = block_p90(amp); Y, X = amp.shape[1:]
    sup = np.empty(amp.shape, bool)
    for i in range(bp.shape[0]):
        thr = np.maximum(tau, 0.25 * np.repeat(np.repeat(bp[i], BLK, 0), BLK, 1)[:Y, :X])
        sup[i * BLK:(i + 1) * BLK] = amp[i * BLK:(i + 1) * BLK] > thr[None]
    return sup, tau


def thickness_hist(unsup):
    """Local thickness proxy of the unsupported region: 2 x max(EDT) within a 5^3 window
    (captures the medial value for gaps thinner than ~2 periods). z-slabs with overlap."""
    Z = unsup.shape[0]; S, O = 40, 12            # small slabs: EDT allocates ~20 B/voxel
    bins = np.arange(0, 5.01, 0.25) * P
    hist = np.zeros(len(bins) - 1, np.int64); thin = 0; tot = 0
    for z0 in range(0, Z, S):
        a, b = max(0, z0 - O), min(Z, z0 + S + O)
        e = ndi.distance_transform_edt(unsup[a:b]).astype(np.float32)
        t = 2 * ndi.maximum_filter(e, size=5)
        core = slice(z0 - a, z0 - a + min(S, Z - z0))
        m = unsup[a:b][core]; tv = t[core][m]
        hist += np.histogram(np.minimum(tv, bins[-1] - 1e-3), bins)[0]
        thin += int((tv < 0.5 * P).sum()); tot += int(m.sum())
    return bins / P, hist, thin / max(tot, 1)


def main():
    t0 = time.time(); res = {}
    slab = np.load(REPO / "data/1667/m1/slab_u8.npy", mmap_mode="r")
    hist = np.zeros(256, np.int64)
    for z in range(0, slab.shape[0], 32):
        hist += np.bincount(np.asarray(slab[z:z + 32]).ravel(), minlength=256)
    otsu = float(threshold_otsu(hist=(hist, np.arange(256))))
    fg = np.asarray(slab) > otsu
    env = np.empty_like(fg)
    for z in range(fg.shape[0]):
        env[z] = ndi.binary_fill_holes(ndi.binary_closing(fg[z], iterations=4))
    res.update(otsu=otsu, fg_frac_of_slab=float(fg.mean()), envelope_voxels=int(env.sum()))
    amp = zarr.open_array(str(M2 / "mono/amp"), mode="r")[...]
    rows = []
    for name in ("raw", "smoothed"):
        if name == "smoothed":                         # separable Gaussian, FWHM = 1 period, ping-pong buffers
            tmp = np.empty_like(amp)
            ndi.gaussian_filter1d(amp, SMOOTH_SIGMA, axis=0, output=tmp)
            ndi.gaussian_filter1d(tmp, SMOOTH_SIGMA, axis=1, output=amp)
            ndi.gaussian_filter1d(amp, SMOOTH_SIGMA, axis=2, output=tmp)
            amp, tmp = tmp, None
        sup, tau = gate(amp, fg)
        sup &= env
        b, h, thin = thickness_hist(env & ~sup)
        lab, n = ndi.label(sup, structure=np.ones((3, 3, 3), bool))
        sizes = np.bincount(lab.ravel())[1:]; order = np.argsort(sizes)[::-1]
        res[name + "_gate"] = dict(tau_abs=tau, support_frac_fg=float(sup[fg].mean()), support_frac_env=float(sup[env].mean()),
                                   unsupported_share_thinner_half_period=thin,
                                   connectivity=dict(structure="26", n_components=int(n), support_voxels=int(sizes.sum()),
                                                     largest_share=float(sizes[order[0]] / sizes.sum()),
                                                     second_share=float(sizes[order[1]] / sizes.sum()) if n > 1 else 0.0,
                                                     n_components_ge_1000_vox=int((sizes >= 1000).sum())))
        rows += [dict(gate=name, lo_periods=round(b[i], 2), hi_periods=round(b[i + 1], 2), voxels=int(h[i])) for i in range(len(h))]
        del lab
        save(f"support_{name}.zarr", sup.astype(np.uint8)); del sup
        print(name, json.dumps(res[name + "_gate"]), flush=True)
    del amp
    use = "smoothed" if res["raw_gate"]["unsupported_share_thinner_half_period"] > 0.30 else "raw"
    res["gate_used"] = use
    import shutil; shutil.copytree(M2 / f"support_{use}.zarr", M2 / "support.zarr", dirs_exist_ok=True)
    save("envelope.zarr", env.astype(np.uint8))
    with open(OUT / "m2_gap_thickness.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    ru = resource.getrusage(resource.RUSAGE_SELF)
    res.update(wall_s=round(time.time() - t0, 1), cpu_s=round(ru.ru_utime + ru.ru_stime, 1), peak_rss_MB=round(ru.ru_maxrss / 1024))
    json.dump(res, open(OUT / "m2_support.json", "w"), indent=1); print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
