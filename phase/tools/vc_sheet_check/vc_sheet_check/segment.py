"""Segment run: one tifxyz or OBJ mesh, no patch set, no joins, no reference (SessA-4 design).

- **Evaluation (SessA-4 (a)).** Dense by default: every pair of mesh vertices whose path along mesh edges is 100-400 um
  (S1b's pair separation, exhaustively), each vertex snapped once to the nearest phase zero of the field and each
  pair counted once for signed sheet crossings (frozen `Field.snap` / `Field.count`). `--pairs-per-cm2` switches to
  S1b-style random sampling at that density; it is the only sampling knob (no floor, no cap).
- **Primary output: per-pair flags with coverage** (`pairs.csv`; `report.json` `coverage`). A pair is *testable* if
  both endpoints snapped and the path stayed in the field's support, and *flagged* if testable with round(count) != 0.
- **Clusters** are DBSCAN(eps 200 um, min_samples m*) on flagged midpoints, with m* derived from the null in SessA-4 (b)
  (`power_calibration.json`). Every run records and prints, next to the cluster count, the estimated probability that
  a 2 mm layer jump would have produced a cluster at this run's density and coverage (`power.py`). Below 0.5 it says
  "not a clean-segment test".
- **Contract.** Region = mesh bbox + halo snapped outward to the 128 grid (Amendment 4 §A4.1). The overlay is the
  full-frame sparse OME-Zarr v2 (value 1 within 3 voxels of a flagged pair's evaluated points). The axis file is
  required (A5.3) and the field is oriented about it. `status` per A4.2.
"""
from __future__ import annotations

import copy
import csv
import json
import resource
import time
from pathlib import Path

import numpy as np

from . import check as CK
from . import field as FLD
from . import meshio
from . import power as PW
from . import sources as SRC
from . import zarrio
from .region import _git, _sha, _js, VOX_UM, CELL_MM2

LEVEL = 1
DEFAULT_M = 5          # S1b's min_samples, used only when no SessA-4 calibration exists (then power is 'unknown')


class InputError(Exception):
    """Invalid input: CLI exit code 2 (CONTRACT A4.2)."""


def snap_region(lo_zyx, hi_zyx, halo_vox, scan_shape):
    """phase/tools/contract_io.snap_region: bbox [lo, hi) plus halo, snapped outward to the 128 grid, clipped."""
    lo = [max(0, int(np.floor((l - halo_vox) / 128)) * 128) for l in lo_zyx]
    hi = [min(s, int(np.ceil((h + halo_vox) / 128)) * 128) for h, s in zip(hi_zyx, scan_shape)]
    return lo, [h - l for l, h in zip(lo, hi)]


def apply_crop(mesh, crop):
    """Check only vertices inside a z,y,x box; for tifxyz cut the grid to the rows/cols holding them."""
    n_all = int(mesh.valid.sum()); area_all = CK.area_cm2(mesh, VOX_UM)
    o = np.array(crop[:3]); e = o + np.array(crop[3:])
    mesh.valid = mesh.valid & ((mesh.xyz[:, ::-1] >= o) & (mesh.xyz[:, ::-1] < e)).all(1)
    mesh.edges = mesh.edges[mesh.valid[mesh.edges[:, 0]] & mesh.valid[mesh.edges[:, 1]]]
    if not mesh.valid.any():
        raise InputError("no mesh vertices inside --crop")
    row0 = col0 = 0
    if mesh.grid is not None:
        H, W = mesh.grid.shape; ok2 = mesh.valid.reshape(H, W)
        rs = np.where(ok2.any(1))[0]; cs = np.where(ok2.any(0))[0]
        row0, col0 = int(rs[0]), int(cs[0]); r1, c1 = int(rs[-1]) + 1, int(cs[-1]) + 1
        g = mesh.xyz.reshape(H, W, 3)[row0:r1, col0:c1].reshape(-1, 3); v = ok2[row0:r1, col0:c1]
        mesh = meshio.Mesh(xyz=g, valid=v.ravel(), edges=meshio._grid_edges(r1 - row0, c1 - col0, v.ravel()), kind="tifxyz",
                           source=mesh.source, grid=np.arange(g.shape[0]).reshape(r1 - row0, c1 - col0), meta=mesh.meta)
    return mesh, dict(origin_zyx=o.tolist(), shape_zyx=list(crop[3:]), vertices_total=n_all, grid_offset_rc=[row0, col0],
                      vertices_checked=int(mesh.valid.sum()), area_total_cm2=area_all)


def run(args, repo):
    t_start = time.time()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    mp = Path(args.mesh)
    if not mp.exists():
        raise InputError(f"mesh not found: {mp}")
    try:
        mesh = meshio.read_mesh(mp)
    except ValueError as e:
        raise InputError(str(e))
    if not mesh.valid.any():
        raise InputError("mesh has no valid vertices")
    name = mp.name; mesh_full = copy.deepcopy(mesh); crop = None
    if getattr(args, "crop", None):
        mesh, crop = apply_crop(mesh, args.crop)
    # axis (A5.3): required; the segment may not leave the file's z range by more than 256 voxels
    if not getattr(args, "axis_file", None):
        raise InputError("an axis file is required in segment mode (CONTRACT A5.3): --axis-file z,y,x")
    af = Path(args.axis_file)
    if not af.exists():
        raise InputError(f"axis file not found: {af}")
    try:
        axis_xy = FLD.load_axis_file(af)                               # A12.1: our z,y,x CSV or villa's umbilicus.json
    except (ValueError, KeyError) as e:
        raise InputError(f"axis file {af}: {e}")
    zr = (float(axis_xy.z[0]), float(axis_xy.z[-1])); vz = mesh.xyz[mesh.valid][:, 2]
    if vz.min() < zr[0] - 256 or vz.max() > zr[1] + 256:
        raise InputError(f"segment z {vz.min():.0f}-{vz.max():.0f} leaves the axis file's z range {zr[0]:.0f}-{zr[1]:.0f} by more than 256")
    inputs = {}
    for f in ([mp / f"{c}.tif" for c in "xyz"] if mp.is_dir() else [mp]):
        inputs[str(f)] = _sha(f)
    inputs[str(af)] = _sha(af)
    inputs[str(args.ct)] = "remote (not hashed)" if str(args.ct).startswith("http") else "local"
    ct = SRC.CT(args.ct, LEVEL)
    scan0 = ct.shape0 or (list(args.scan_shape) if getattr(args, "scan_shape", None) else None)
    if scan0 is None:
        raise InputError("a local CT crop does not give the scan shape; pass --scan-shape")
    period_um = getattr(args, "period_um", None) or FLD.PERIOD_UM
    halo_l0 = FLD.halo_voxels(getattr(args, "halo_um", None) or FLD.HALO_UM)
    lo, hi = mesh.bbox()
    blo, bhi = FLD.box_for_mesh(lo, hi, halo_l0, LEVEL, scan0)
    org, shp = snap_region(np.floor(lo[::-1]).astype(int), np.floor(hi[::-1]).astype(int) + 1, halo_l0, scan0)
    work = out / "_work"; t0 = time.time()
    fm = FLD.build(ct, LEVEL, VOX_UM, blo, bhi, work / "field", period_um=period_um, axis_xy=axis_xy, axis_tag=str(af))
    t_field = time.time() - t0
    from ._vendor import mesh_check
    fld = mesh_check().bind_field(str(work / "field"), fm); snap = fm["period_vox"] * 2 ** LEVEL
    # evaluation
    t0 = time.time()
    rho_req = getattr(args, "pairs_per_cm2", None)
    if rho_req is None:
        res = CK.run_dense(mesh, fld, snap, VOX_UM); mode = "dense"
    else:
        A = CK.area_cm2(mesh, VOX_UM)
        res = CK.run_check(mesh, fld, snap, VOX_UM, name, n_pairs=int(round(A * rho_req))); mode = f"sampled {rho_req:g}/cm2"
        res["geodesic_um"] = np.full(len(res["ia"]), np.nan)
    t_eval = time.time() - t0
    ia, ib = res["ia"], res["ib"]; counts, ok = res["counts"], res["ok"]
    mid = res["mid"].astype(np.float64); pa = res["pa"].astype(np.float64); pb = res["pb"].astype(np.float64)
    good = ok & np.isfinite(counts); flag = good & (np.round(counts) != 0)
    area = res["area_cm2"]; n_pairs = int(len(ia))
    rho = n_pairs / area if area > 0 else 0.0; cshare = float(good.mean()) if n_pairs else 0.0
    cal = PW.load(); m = cal["m_star"] if cal else DEFAULT_M
    lab = CK.clusters_at(mid, flag, VOX_UM, m) if flag.any() else np.zeros(0, int)
    pw = PW.estimate(rho, cshare, cal)

    git, branch = _git(repo)
    head = dict(contract="v1", git=git, region=dict(origin_zyx=org, shape_zyx=shp))
    # per-pair flags (the primary product)
    with open(out / "pairs.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["vertex_a", "vertex_b", "mid_z", "mid_y", "mid_x", "geodesic_um", "testable", "count", "flagged", "cluster"])
        cl_of = np.full(n_pairs, -1); cl_of[np.where(flag)[0]] = lab
        for i in range(n_pairs):
            w.writerow([int(ia[i]), int(ib[i]), round(mid[i, 2], 2), round(mid[i, 1], 2), round(mid[i, 0], 2),
                        "" if not np.isfinite(res["geodesic_um"][i]) else round(float(res["geodesic_um"][i]), 1), int(good[i]),
                        "" if not np.isfinite(counts[i]) else int(round(counts[i])), int(flag[i]), int(cl_of[i])])
    # suspect vertices: within 3 voxels of a flagged pair's evaluated points (PA, PB, midpoint; CONTRACT §4.3)
    from scipy.spatial import cKDTree
    ev = np.concatenate([pa[flag], pb[flag], mid[flag]]) if flag.any() else np.zeros((0, 3))
    valid = np.where(mesh.valid)[0]; suspect = np.zeros(len(mesh.xyz), bool)
    if len(ev):
        d, _ = cKDTree(ev).query(mesh.xyz[valid], distance_upper_bound=3.0); suspect[valid[np.isfinite(d)]] = True
    H, Wd = mesh.grid.shape if mesh.grid is not None else (None, None)
    with open(out / "vertices.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow("patch,row,col,z,y,x,wrap_index,theta,page,page_majority_n,n_ref,ref_ok,wrong_turn,suspect,max_risk".split(","))
        for i in valid:
            x, y, z = mesh.xyz[i]; r, c = (divmod(int(i), Wd) if Wd else (int(i), ""))
            if Wd and crop:
                r, c = r + crop["grid_offset_rc"][0], c + crop["grid_offset_rc"][1]
            w.writerow([0, r, c, round(float(z), 2), round(float(y), 2), round(float(x), 2), "", "", "", "", "", 0, 0, int(suspect[i]), ""])
    # overlay (Amendment 4): value 1 within 3 voxels of flagged pairs' evaluated points
    blocks = zarrio.spheres_to_blocks(ev[:, ::-1] if len(ev) else ev, 3.0, 1, org, shp)
    zarrio.write_overlay_fullframe_sparse(out / "overlay.zarr", blocks, scan0, org, shp, name=f"vc_sheet_check {name}",
                                          extra_attrs=dict(values={"0": "none", "1": "flagged pair (per-pair flag)"}))
    # clusters (reported with the power statement) and cleaning: vertices of clustered pairs
    clusters = []; remove = np.zeros(len(mesh.xyz), bool); fl_idx = np.where(flag)[0]
    for L in sorted(set(lab.tolist()) - {-1}):
        mem = fl_idx[lab == L]; P3 = np.concatenate([pa[mem], pb[mem], mid[mem]])[:, ::-1]
        verts = np.unique(np.r_[ia[mem], ib[mem]]); remove[verts] = True
        th = np.degrees(np.angle(np.mean(np.exp(1j * np.arctan2(mid[mem, 1] - axis_xy(mid[mem, 2])[1], mid[mem, 0] - axis_xy(mid[mem, 2])[0]))))) % 360
        clusters.append(dict(id=len(clusters), kind="suspect_join", check="segment-mode per-pair crossing count", n_pairs=int(len(mem)),
                             n_patches=1, area_cm2=float(len(verts) * CELL_MM2 / 100) if mesh.grid is not None else None,
                             centroid_zyx=P3.mean(0).round(2).tolist(), bbox_zyx=[P3.min(0).round(2).tolist(), P3.max(0).round(2).tolist()],
                             theta_deg=round(float(th), 2), wrap_index_range=None, patches=[0],
                             pairs=[[int(ia[k]), int(ib[k])] for k in mem], max_risk=None))
    cleaned = _write_cleaned(out, mesh, mesh_full, crop, remove, inputs, mp, git)
    ru = resource.getrusage(resource.RUSAGE_SELF)
    coverage = dict(mode=mode, pairs=n_pairs, area_cm2=area, pairs_per_cm2=rho, testable=int(good.sum()), testable_share=cshare,
                    flagged=int(flag.sum()), flagged_per_cm2=float(flag.sum() / area) if area else None,
                    flagged_share_of_testable=float(flag.sum() / good.sum()) if good.any() else None)
    rep = dict(**head, status="ok", branch=branch, inputs=inputs, axis_file=axis_xy.report(), axis_queries_outside=axis_xy.outside,
               counts=dict(patches=1, patches_with_wrap_index=0, wrap_components=0, joins=0, pairs_scored=n_pairs,
                           pairs_flagged=int(flag.sum()), pairs_flagged_contact=0, pages=0, wrong_turn_patches=0, wrong_turn_points=0),
               areas_cm2=dict(patches_bbox=None, pages=None, flagged_suspect=float(suspect.sum() * CELL_MM2 / 100) if mesh.grid is not None else None,
                              wrong_turn=None, cleaned_kept=cleaned.get("kept_cm2")),
               metrics={}, clusters=clusters, coverage=coverage,
               cluster_rule=dict(eps_um=CK.EPS_UM, min_samples=m, source="SessA-4 null (power_calibration.json)" if cal else "S1b default (no calibration)"),
               power=pw,
               method=dict(mode="segment", evaluation=mode, mesh_kind=mesh.kind, crop=crop, vertices=int(mesh.valid.sum()),
                           field={k: fm[k] for k in fm if k != "done"}, halo_l0=halo_l0, period_um=period_um, level=LEVEL,
                           axis=str(af), cleaned=cleaned,
                           note=("Segment mode's product is the per-pair flags with coverage (pairs.csv). Cluster counts are "
                                 "reported with the power statement; below 0.5 they are not a clean-segment test. "
                                 "counts.pairs_flagged_contact is 0 because contact (sep_um < 50) is a region-mode pair property."),
                           empty_fields="wrap_index, theta, page, page_majority_n, n_ref, max_risk: undefined for a single segment"),
               resources=dict(wall_s=round(time.time() - t_start, 1), field_s=round(t_field, 1), evaluation_s=round(t_eval, 1),
                              cpu_s=round(ru.ru_utime + ru.ru_stime, 1), max_rss_mb=round(ru.ru_maxrss / 1024, 1),
                              field_voxels=int(np.prod(fm["shape"]))))
    json.dump(rep, open(out / "report.json", "w"), indent=1, default=_js)
    print(f"clusters: {len(clusters)} (DBSCAN eps 200 um, min_samples {m}) -- {pw['statement']}", flush=True)
    print(f"coverage: {coverage['testable']}/{n_pairs} pairs testable ({100 * cshare:.1f} %), {coverage['flagged']} flagged, "
          f"{rho:.0f} pairs/cm2 ({mode})", flush=True)
    if not getattr(args, "keep_work", False):
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    return rep


def _write_cleaned(out, mesh, mesh_full, crop, remove, inputs, mp, git):
    if mesh.grid is not None:
        rm_full = np.zeros(len(mesh_full.xyz), bool); idx = np.where(remove & mesh.valid)[0]
        if len(idx):
            Wsub = mesh.grid.shape[1]; Wf = mesh_full.grid.shape[1]; r0, c0 = crop["grid_offset_rc"] if crop else (0, 0)
            rr, cc = np.divmod(idx, Wsub); rm_full[(rr + r0) * Wf + (cc + c0)] = True
        d = out / "cleaned" / "segment" / "patch_0"
        meshio.write_tifxyz(d, mesh_full, ~rm_full, dict(contract="v1", git=git, removed_cells=int(rm_full.sum()), format="tifxyz",
                                                        source_sha256={c: inputs[str(mp / f"{c}.tif")] for c in "xyz"},
                                                        cleaning_rule="segment mode: vertices of clustered flagged pairs"))
        kept = int((mesh.valid & ~remove).sum())
        return dict(format="tifxyz", removed_cells=int(rm_full.sum()), kept_cm2=kept * CELL_MM2 / 100)
    keepv = mesh_full.valid & ~remove; f_ok = keepv[mesh.faces].all(1)
    (out / "cleaned").mkdir(exist_ok=True)
    with open(out / "cleaned" / "segment.obj", "w") as f:
        f.write(f"# vc_sheet_check cleaned OBJ, contract v1, git {git}; removed vertices {int((remove & mesh.valid).sum())}\n")
        for v_ in mesh.xyz:
            f.write(f"v {v_[0]:.4f} {v_[1]:.4f} {v_[2]:.4f}\n")
        for a, b, c in mesh.faces[f_ok] + 1:
            f.write(f"f {a} {b} {c}\n")
    return dict(format="obj (no tifxyz grid)", removed_vertices=int((remove & mesh.valid).sum()), faces_kept=int(f_ok.sum()),
                faces_removed=int((~f_ok).sum()), kept_cm2=None)
