"""Tiled witness for region mode (SessA-6): fields over a set's full extent without holding one big field in RAM.

The region's witness pair points are assigned to tiles by midpoint. Each tile has a core (default 768 x 512 x 512 L0,
z y x, anchored at the region origin). A tile's field covers core + halo (the contract halo, 48 L0) at level 1, the
given period, and orientation about the scroll axis, exactly as a single-box field would (field.build). Only tiles whose
core holds a pair midpoint are built. Each point is evaluated in its own tile with witness_stable's definitions
(normal separation > 1 voxel, snap both ends, deterministic signed crossing count). A path or snap that leaves the tile's
box samples out of support and is untestable, and is counted in `left_box`.

Workers are separate processes (one bound field per process: the vendored Field reads a module-level transform).
Output: W = dict(ia, cs, pi, sep) over the whole region, the same layout as switchwitness witness(), plus per-tile stats.
"""
from __future__ import annotations

import json
import os
import resource
import shutil
import time
from pathlib import Path

import numpy as np

LEVEL = 1


def _quiet(*a, **k):
    pass


def tile_index(mid_xyz, org_zyx, core_zyx):
    return np.floor((mid_xyz[:, ::-1] - np.asarray(org_zyx)) / np.asarray(core_zyx)).astype(int)


def _one_tile(job):
    from . import field as FLD, sources as SRC
    from .check import count_dense
    from ._vendor import mesh_check
    t0 = time.time(); c0 = time.process_time()
    gate = job["gate"]
    ct = FLD.LocalCT(gate["raw_path"], gate["raw_origin"]) if gate.get("raw_path") else SRC.CT(job["ct"], LEVEL)
    lo_l0 = np.asarray(job["core_lo_zyx"]); hi_l0 = lo_l0 + np.asarray(job["core_zyx"])
    blo, bhi = FLD.box_for_mesh(lo_l0[::-1], hi_l0[::-1] - 1, job["halo_l0"], LEVEL, job["scan_shape"])
    axis = FLD.load_axis_file(job["axis_file"])
    fm = FLD.build(ct, LEVEL, 7.91, blo, bhi, job["fdir"], period_um=job["period_um"], axis_xy=axis, axis_tag=job["axis_tag"],
                   gate=job["gate"])
    t_field = time.time() - t0; c_field = time.process_time() - c0
    fld = mesh_check().bind_field(job["fdir"], fm)
    d = np.load(job["pts"]); PA, PB, gi = d["PA"], d["PB"], d["gi"]
    per0 = fm["period_vox"] * 2 ** LEVEL
    sep = np.abs(np.sum((PB - PA) * fld.normal((PA + PB) / 2), 1)); k = np.where(sep > 1)[0]
    sa, _ = fld.snap(PA[k], tmax=per0); sb, _ = fld.snap(PB[k], tmax=per0)
    S = np.concatenate([sa, sb]); n = len(k)
    c_, o_ = count_dense(fld, S, np.arange(n), np.arange(n, 2 * n))
    cs = np.full(n, np.nan); cs[o_] = np.rint(c_[o_])
    # points whose ends or path leave the tile's box (level-1 box -> L0 xyz)
    s = 2 ** LEVEL; blo0 = np.asarray(blo)[::-1] * s; bhi0 = np.asarray(bhi)[::-1] * s
    inb = lambda X: np.all((X >= blo0) & (X < bhi0), 1)
    left = int((~(inb(PA[k]) & inb(PB[k]))).sum())
    np.savez(job["res"], gi=gi[k], cs=cs, sep=sep[k])
    ru = resource.getrusage(resource.RUSAGE_SELF)
    st = dict(tile=job["tile"], box_l1_origin=blo, box_l1_shape=[b - a for a, b in zip(blo, bhi)], points=int(len(PA)),
              evaluated=int(n), testable=int(np.isfinite(cs).sum()), left_box=left, field_wall_s=round(t_field, 1),
              field_cpu_s=round(c_field, 1), wall_s=round(time.time() - t0, 1), cpu_s=round(time.process_time() - c0, 1),
              max_rss_mb=round(ru.ru_maxrss / 1024, 1), pull=fm.get("pull"), period_vox=fm.get("period_vox"))
    if not job.get("keep"):
        shutil.rmtree(job["fdir"], ignore_errors=True)
    return st


def tiled_witness(P, ct_spec, org_zyx, shape_zyx, work, axis_file, period_um, halo_l0, scan_shape,
                  core_zyx=(768, 512, 512), workers=3, cpu_cap_s=None, keep=False, log=print, gate=None, gate_mode="region",
                  gate_workers=4, deadline_unix=None):
    """P: switchwitness pairs() dict (PA, PB, PI in L0 x,y,z). Returns W, stats.
    gate: field.region_gate() result; computed here over the tiles' union box when not given (one support rule for
    every tile; a per-tile adaptive gate changes support with tile size, measured on fixture A in SessA-6).
    gate_mode "band" (SessA-12, whole scroll): one gate per z band of tiles, over that band's union of tile boxes + halo --
    X3's slab-box statistics, slab 2 being one such band -- with the band's CT cached once and read by its tiles.
    deadline_unix: no new tile starts after it; finished tiles are kept (partial run, reported)."""
    from multiprocessing import get_context
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    PA, PB, PI = P["PA"].astype(np.float64), P["PB"].astype(np.float64), P["PI"]
    mid = (PA + PB) / 2
    ti = tile_index(mid, org_zyx, core_zyx)
    keys, inv = np.unique(ti, axis=0, return_inverse=True); inv = inv.ravel()
    from . import field as FLD
    band_gate = {}
    if gate is None and gate_mode == "band":
        def band_box(kz):
            kk = keys[keys[:, 0] == kz]
            lo_t = np.asarray(org_zyx) + np.r_[kz, kk[:, 1].min(), kk[:, 2].min()] * np.asarray(core_zyx) - halo_l0
            hi_t = np.asarray(org_zyx) + np.r_[kz + 1, kk[:, 1].max() + 1, kk[:, 2].max() + 1] * np.asarray(core_zyx) + halo_l0
            return np.maximum(lo_t, 0).tolist(), np.minimum(hi_t, np.asarray(scan_shape)).tolist()
        bands = sorted({int(k[0]) for k in keys})
        todo = []
        for kz in bands:
            gf = work / f"gate_band{kz}" / "region_gate.json"
            if gf.exists():
                band_gate[kz] = json.load(open(gf))
            else:
                lo_b, hi_b = band_box(kz); todo.append((kz, lo_b, hi_b))
        if todo:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(min(gate_workers, len(todo)), mp_context=get_context("fork")) as ex:
                futs = {kz: ex.submit(FLD.region_gate, ct_spec, lo_b, hi_b, period_um, work / f"gate_band{kz}", LEVEL, 16, 0, 128, _quiet, True)
                        for kz, lo_b, hi_b in todo}
                for kz, f in futs.items():
                    band_gate[kz] = f.result()
                    json.dump(band_gate[kz], open(work / f"gate_band{kz}" / "region_gate.json", "w"))
                    log(f"[tiled] band {kz} gate: otsu {band_gate[kz]['otsu']:.0f} tau {band_gate[kz]['tau']:.1f} env {band_gate[kz]['env_frac']:.3f}")
        gate = {"mode": "band", "bands": {str(k): {kk: vv for kk, vv in v.items() if kk not in ("env_path", "raw_path")} for k, v in band_gate.items()}}
    elif gate is None:
        lo_t = np.asarray(org_zyx) + keys.min(0) * np.asarray(core_zyx) - halo_l0
        hi_t = np.asarray(org_zyx) + (keys.max(0) + 1) * np.asarray(core_zyx) + halo_l0
        lo_t = np.maximum(lo_t, 0); hi_t = np.minimum(hi_t, np.asarray(scan_shape))
        c0 = time.process_time()
        gate = FLD.region_gate(ct_spec, lo_t.tolist(), hi_t.tolist(), period_um, work / "gate", level=LEVEL)
        gate["cpu_s"] = round(time.process_time() - c0, 1)
    jobs = []
    for j, key in enumerate(keys):
        g = np.where(inv == j)[0]
        core_lo = (np.asarray(org_zyx) + key * np.asarray(core_zyx)).tolist()
        tag = "t_%d_%d_%d" % tuple(key)
        res = work / f"{tag}.npz"; pts = work / f"{tag}_pts.npz"
        np.savez(pts, PA=PA[g], PB=PB[g], gi=g)
        jobs.append(dict(tile=tag, core_lo_zyx=core_lo, core_zyx=list(core_zyx), halo_l0=halo_l0, scan_shape=list(scan_shape),
                         ct=str(ct_spec), axis_file=str(axis_file), axis_tag=f"axis file {Path(axis_file).name}",
                         period_um=period_um, gate=band_gate.get(int(key[0]), gate), fdir=str(work / f"{tag}_field"), pts=str(pts), res=str(res), keep=keep, n=len(g)))
    # largest tiles first so the pool drains evenly
    jobs.sort(key=lambda j: -j["n"])
    log(f"[tiled] {len(PA)} points in {len(jobs)} tiles (core {list(core_zyx)} L0, halo {halo_l0})")
    stats, done_cpu, skipped = [], 0.0, []
    pending = [j for j in jobs if not Path(j["res"]).exists() or not Path(j["res"] + ".json").exists()]
    for j in jobs:
        if j not in pending:
            stats.append(json.load(open(j["res"] + ".json"))); done_cpu += stats[-1]["cpu_s"]
    with get_context("fork").Pool(workers, maxtasksperchild=1) as pool:
        its = pool.imap_unordered(_one_tile, pending)
        for st in its:
            if deadline_unix and time.time() > deadline_unix:
                log("[tiled] deadline passed: no further tiles (partial run)"); pool.terminate(); skipped.append("deadline"); break
            json.dump(st, open(work / f"{st['tile']}.npz.json", "w"))
            stats.append(st); done_cpu += st["cpu_s"]
            log(f"[tiled] {st['tile']}: {st['points']} pts, {st['testable']}/{st['evaluated']} testable, left box {st['left_box']}, "
                f"field {st['field_cpu_s']} CPU-s, rss {st['max_rss_mb']} MB; cumulative {done_cpu / 3600:.2f} CPU-h")
            if cpu_cap_s and done_cpu > cpu_cap_s:
                log(f"[tiled] CPU cap {cpu_cap_s} s passed: no further tiles (protocol stop rule)")
                pool.terminate(); break
    ia, cs, sep, pi = [], [], [], []
    for j in jobs:
        if not Path(j["res"]).exists():
            skipped.append(j["tile"]); continue
        d = np.load(j["res"]); ia.append(d["gi"]); cs.append(d["cs"]); sep.append(d["sep"])
    ia = np.concatenate(ia) if ia else np.zeros(0, int); o = np.argsort(ia, kind="stable")
    W = dict(ia=ia[o], cs=np.concatenate(cs)[o] if cs else np.zeros(0), sep=np.concatenate(sep)[o] if sep else np.zeros(0))
    W["pi"] = PI[W["ia"]]
    if band_gate and not keep:
        for v in band_gate.values():
            Path(v["raw_path"]).unlink(missing_ok=True)
    return W, dict(gate={k: v for k, v in gate.items() if k != "env_path"}, tiles=stats, n_tiles=len(jobs), tiles_not_built=skipped, core_zyx=list(core_zyx), halo_l0=halo_l0,
                   period_um=period_um, level=LEVEL, cpu_s=round(sum(s["cpu_s"] for s in stats), 1),
                   points=int(len(PA)), evaluated=int(len(W["ia"])), testable=int(np.isfinite(W["cs"]).sum()),
                   left_box=int(sum(s["left_box"] for s in stats)))
