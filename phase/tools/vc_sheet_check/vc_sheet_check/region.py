"""Region run (contract v1 §4): patches in a region -> report.json, overlay.zarr, vertices.csv, cleaned/.

Pipeline, each step named with its source of truth:
  1. patches meeting the region (bbox test) and their tifxyz grids;
  2. witness pairs (switchwitness pairs(), vendored) and a fixed-80-um field on the bbox of
     their points plus a halo (field.py);
  3. features (features.py) and the switch score (default risk_model_v2_noz, SessA-7; the fixture uses v1); flag = risk >= its blind threshold.
     If a committed feature table is given (--features), flags come from it (reproduction mode,
     required for the fixture golden check) and the recomputed features are written alongside
     with their agreement; otherwise flags come from the recomputed features;
  4. wrap index = Q3c's committed values (contract §2; recomputing the LP solve on new data is
     outside SessA and is reported as such);
  5. joins = rel.csv minus flip=1-only pairs; (iii-rf) = cut-adjusted wrap difference 0 and direct
     measurement absent or 0 (p1b_rf_joins.py's rule); page joins = (iii-rf) minus flagged joins;
  6. pages and metrics from phase/tools/metrics.py only; wrong-turn points = §5.4 minority points;
  7. writers.
"""
from __future__ import annotations

import csv
import hashlib
import json
import resource
import subprocess
import time
from pathlib import Path

import numpy as np

from . import sources as SRC
from . import features as FE
from . import field as FLD
from . import zarrio

VOX_UM = 7.91
CELL_MM2 = (4 * VOX_UM) ** 2 / 1e6
HALO_L0 = 48
LEVEL = 1
CLUSTER_VOX = 50 / VOX_UM          # §4.1 single linkage, 6.32 voxels


def _sha(p):
    """SHA-256 of a file; for a directory (a folder of patch_N/ tifxyz), of every file's relative path and bytes in
    sorted order ("tree:" prefix)."""
    p = Path(p); h = hashlib.sha256()
    files = sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir() else [p]
    for q in files:
        if p.is_dir():
            h.update(str(q.relative_to(p)).encode() + b"\0")
        with open(q, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
    return ("tree:" if p.is_dir() else "") + h.hexdigest()


def _git(repo):
    """Head and branch; '+dirty' when the tool's own files differ from the head (the run is then not exactly that commit)."""
    r = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True, cwd=repo).stdout.strip()
    dirty = bool(r("status", "--porcelain", "--untracked-files=no", "--", "phase/tools/vc_sheet_check", "phase/tools/pipeline9_filter"))
    return r("rev-parse", "HEAD") + ("+dirty" if dirty else ""), r("rev-parse", "--abbrev-ref", "HEAD")


def jkey(a, b):
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


def _cross(t1, t2):
    e = t1 + (np.mod(t2 - t1 + np.pi, 2 * np.pi) - np.pi)
    return 1 if e >= 2 * np.pi else (-1 if e < 0 else 0)


def rf_joins(joins, K, s, direct):
    """p1b_rf_joins.py's rule: keep iff an end has no wrap index, or the cut-adjusted wrap difference is 0 and the
    direct measurement (d_i else d_ii) is absent or 0."""
    kept = []
    for a, b in joins:
        if a in K and b in K:
            dk = K[b][0] - K[a][0] - s * _cross(K[a][1], K[b][1])
            d = direct.get((a, b))
            ok = dk == 0 and (d is None or d == 0)
        else:
            ok = True
        if ok:
            kept.append((a, b))
    return kept


def _direct_from_edges(path):
    out = {}
    if not path or not Path(path).exists():
        return out
    for r in csv.DictReader(open(path)):
        for c in ("d_i", "d_ii"):
            x = r.get(c)
            if x not in (None, "", "None"):
                out[jkey(r["patch_a"], r["patch_b"])] = int(float(x)); break
    return out


class UF:
    def __init__(s): s.p = {}
    def f(s, x):
        s.p.setdefault(x, x)
        while s.p[x] != x:
            s.p[x] = s.p[s.p[x]]; x = s.p[x]
        return x
    def u(s, a, b): s.p[s.f(a)] = s.f(b)


def run(args, repo):
    t_start = time.time()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    M = _metrics(repo)
    org = list(args.origin); shp = list(args.shape)
    if any(o % 128 for o in org):
        raise SystemExit("region origin must be a multiple of 128 (contract §4.2)")
    inputs = {}
    def use(p):
        if p and Path(p).exists():
            inputs[str(p)] = _sha(p)
        return p

    # 1. patches
    for p in args.patches:
        use(p)
    if args.patch_table:
        rows_all = SRC.read_table(use(args.patch_table))
        ids = set(SRC.patches_meeting(rows_all, org, shp))
        G, where = SRC.load_patches(args.patches, ids)
        rows = [r for r in rows_all if int(r["id"]) in ids and int(r["id"]) in G]
    else:
        G_all, where = SRC.load_patches(args.patches)
        rows_all = SRC.patch_table(G_all)
        ids = set(SRC.patches_meeting(rows_all, org, shp))
        G = {p: G_all[p] for p in ids}; rows = [r for r in rows_all if int(r["id"]) in ids]
    allp = sorted(int(r["id"]) for r in rows); S = set(allp)
    area = {int(r["id"]): max(0.0, float(r["xmax"]) - float(r["xmin"])) * max(0.0, float(r["ymax"]) - float(r["ymin"])) * VOX_UM ** 2 / 1e6
            for r in rows_all}
    print(f"[region] {len(allp)} patches meet the region", flush=True)

    # 2-3. field, witness features, risk
    timing = {}; field_meta = None; feats_re = []; W = P = meta = None
    cache = out / "_work"
    if not args.no_field:
        t0 = time.time()
        P, meta = FE.enumerate_pairs(rows, G, cache / "pairs")
        timing["pairs_s"] = round(time.time() - t0, 1)
        ct = SRC.CT(use_url(args.ct, inputs), LEVEL)
        lo, hi = FE.points_bbox(P, 0)
        vol0_shape = ct.shape0 or [10 ** 6] * 3
        period_um = getattr(args, "period_um", None) or FLD.PERIOD_UM
        halo_l0 = FLD.halo_voxels(getattr(args, "halo_um", None) or FLD.HALO_UM)
    if not args.no_field and getattr(args, "tile_core", None):
        from . import tiled as TL
        axis_file = getattr(args, "axis_file", None) or _write_axis_file(cache / "axis_zyx.txt", _axis(repo, args, rows_all), vol0_shape[0])
        t0 = time.time()
        W, tst = TL.tiled_witness(P, args.ct, org, shp, cache / "tiles", axis_file, period_um, halo_l0, vol0_shape,
                                  core_zyx=args.tile_core, workers=getattr(args, "workers", 3),
                                  cpu_cap_s=(args.field_cpu_cap_h * 3600) if getattr(args, "field_cpu_cap_h", None) else None,
                                  keep=args.keep_work)
        timing["tiled_field_witness_s"] = round(time.time() - t0, 1)
        field_meta = dict(tiled=tst, period_um=period_um, halo_l0=halo_l0, level=LEVEL, axis_file=str(axis_file))
        stevens = FE.load_stevens(use(args.badpatchscores))
        feats_re, W = FE.witness_features(P, meta, rows, None, None, cache / "pairs", stevens, W=W)
    elif not args.no_field:
        blo, bhi = FLD.box_for_mesh(lo, hi, halo_l0, LEVEL, vol0_shape)
        if not ct.http:            # a local crop: clip the box to the CT actually present, and say so
            clo, chi = ct.coverage_box_l0(); s_ = 2 ** LEVEL
            blo = [max(a, c // s_) for a, c in zip(blo, clo)]; bhi = [min(b, c // s_) for b, c in zip(bhi, chi)]
            timing["field_box_clipped_to_local_ct"] = True
        t0 = time.time()
        _metrics(repo)
        field_meta = FLD.build(ct, LEVEL, VOX_UM, blo, bhi, cache / "field", period_um=period_um,
                               axis_xy=_axis(repo, args, rows_all), axis_tag=f"refmesh.build_axis rule, --axis {args.axis}")
        field_meta["halo_l0"] = halo_l0
        timing["field_s"] = round(time.time() - t0, 1)
        from ._vendor import mesh_check
        fld = mesh_check().bind_field(str(cache / "field"), field_meta)
        stevens = FE.load_stevens(use(args.badpatchscores))
        t0 = time.time()
        feats_re, W = FE.witness_features(P, meta, rows, fld, field_meta["period_vox"] * 2 ** LEVEL, cache / "pairs", stevens)
        timing["witness_s"] = round(time.time() - t0, 1)
    # SessA-7: default switch score is the z-free refit (risk_model_v2_noz, same folds and threshold rule as v1, no absolute
    # z_um); the fixture keeps v1, which its golden files are built on. --risk-model overrides.
    model = Path(getattr(args, "risk_model", None) or (Path(repo) / "phase/tools/risk_model/risk_model_v2_noz.joblib")); use(model)
    if feats_re and not args.features:
        # stevens_dist_vox from pipeline9 when given; else NaN (the model accepts NaN, contract §3)
        pr, thr, active = FE.score(feats_re, model)
        for f, p in zip(feats_re, pr):
            f["risk"] = float(p); f["flagged"] = int(p >= thr)
    if args.features:
        fc = [r for r in csv.DictReader(open(use(args.features))) if int(r["patch_a"]) in S and int(r["patch_b"]) in S]
        # the committed table's stevens_dist_vox fills the recomputed rows (pipeline9's, not field-dependent)
        st = {jkey(r["patch_a"], r["patch_b"]): r["stevens_dist_vox"] for r in fc}
        for f in feats_re:
            v = st.get((f["patch_a"], f["patch_b"]))
            if v not in (None, "", "nan"):
                f["stevens_dist_vox"] = float(v)
        pc_, thr, active = FE.score(fc, model)
        scored = [dict(patch_a=jkey(r["patch_a"], r["patch_b"])[0], patch_b=jkey(r["patch_a"], r["patch_b"])[1],
                       risk=float(p), flagged=int(p >= thr), sep_um=float(r["sep_um"])) for r, p in zip(fc, pc_)]
        if feats_re:
            pr, _, _ = FE.score(feats_re, model)
            for f, p in zip(feats_re, pr):
                f["risk"] = float(p); f["flagged"] = int(p >= thr)
        flag_source = "committed features (--features): reproduction mode"
    else:
        scored = [dict(patch_a=f["patch_a"], patch_b=f["patch_b"], risk=f["risk"], flagged=f["flagged"], sep_um=f["sep_um"])
                  for f in feats_re]
        thr = FE.score([], model)[1] if not feats_re else thr
        flag_source = "recomputed features (this run's field)"
    flagged = {(r["patch_a"], r["patch_b"]) for r in scored if r["flagged"]}
    risk = {(r["patch_a"], r["patch_b"]): r["risk"] for r in scored}
    sep = {(r["patch_a"], r["patch_b"]): r["sep_um"] for r in scored}
    maxrisk = {}
    for (a, b), p in risk.items():
        for q in (a, b):
            maxrisk[q] = max(maxrisk.get(q, 0.0), p)
    feat_cmp = _compare_features(feats_re, scored) if (feats_re and args.features) else None

    # 4. wrap index: solved from this region's witness (--solve), else the committed Q3c values
    solve_info = None
    if getattr(args, "solve", False):
        K, s_hand, solve_info, solve_direct = _solve(args, repo, out, P, meta, W, rows, G, allp, org, shp, use)
    else:
        K = {int(r["patch"]): (int(r["k_q3c"]), float(r["thN"]), r["component"]) for r in csv.DictReader(open(use(args.wrap_index)))}
        s_hand = json.load(open(Path(args.wrap_index).with_suffix(".json")))["s_chosen"] if Path(args.wrap_index).with_suffix(".json").exists() else 1

    # 5. joins
    flip1 = {jkey(*r[:2]) for r in csv.reader(open(use(args.flip1)))} if args.flip1 else set()
    rel_rows = list(csv.reader(open(use(args.rel))))
    joins = sorted({jkey(*r[:2]) for r in rel_rows} - flip1)
    joins = [k for k in joins if k[0] in S and k[1] in S]
    direct = solve_direct if solve_info else _direct_from_edges(use(args.edges))
    rf = rf_joins(joins, {p: v[:2] for p, v in K.items()}, s_hand, direct)
    E = [k for k in rf if k not in flagged]
    pl = M.pages(E, allp, area, args.page_min_mm2)
    page_of = {p: i for i, c in enumerate(pl) for p in c}

    # 6. points, theta, reference, wrong turn
    axis_xy = _axis(repo, args, rows_all)
    from refmesh import ang  # phase/h1 on sys.path via _metrics
    pts, rc = {}, {}
    for p in allp:
        g = G[p]; valid = np.isfinite(g).all(-1) & (g[..., 0] > 0) & (g[..., 2] > 0)
        rr, cc = np.where(valid); rc[p] = (rr, cc); pts[p] = g[rr, cc]
    th = {p: ang(pts[p], axis_xy) for p in allp}
    tr, okp = {}, {}
    tree = None
    if args.reference:
        from scipy.spatial import cKDTree
        RS = np.load(use(args.reference)); tree = cKDTree(RS["xyz"].astype(np.float64)); RT = RS["t_ref"].astype(np.float64)
        for p in allp:
            d, j = tree.query(pts[p], distance_upper_bound=60 / VOX_UM); m = np.isfinite(d)
            tt = np.full(len(d), np.nan); tt[m] = RT[j[m]]; tr[p] = tt; okp[p] = m
    else:
        for p in allp:
            tr[p] = np.full(len(pts[p]), np.nan); okp[p] = np.zeros(len(pts[p]), bool)
    nref, maj = {}, {}
    for i, c in enumerate(pl):
        tmed = {p: float(np.angle(np.mean(np.exp(1j * th[p])))) % M.TWO_PI for p in c}
        off = M.unwrap_page_theta(c, E, tmed); allv = []
        for p in c:
            thu = tmed[p] + (np.mod(th[p] - tmed[p] + np.pi, M.TWO_PI) - np.pi) + off[p]
            n = np.full(len(th[p]), np.iinfo(np.int64).min); n[okp[p]] = np.round(tr[p][okp[p]] - thu[okp[p]] / M.TWO_PI).astype(int)
            nref[p] = n; allv.append(n[okp[p]])
        allv = np.concatenate(allv) if allv else np.zeros(0, int)
        if len(allv):
            v, cnt = np.unique(allv, return_counts=True); maj[i] = int(v[np.argmax(cnt)])
    wrong = {}
    for p in allp:
        pg = page_of.get(p)
        wrong[p] = (okp[p] & (nref[p] != maj[pg])) if (pg is not None and pg in maj) else np.zeros(len(pts[p]), bool)

    # evaluated points of flagged pairs (x, y, z): X6's when given, else the witness's own
    ev, ev_pair = _evaluated_points(args, flagged, feats_re, W, P, meta, use)
    from scipy.spatial import cKDTree
    evtree = cKDTree(ev) if len(ev) else None
    suspect = {p: (np.isfinite(evtree.query(pts[p], distance_upper_bound=3.0)[0]) if evtree is not None else np.zeros(len(pts[p]), bool)) for p in allp}

    # 7. writers
    git, branch = _git(repo)
    head = dict(contract="v1", git=git, region=dict(origin_zyx=org, shape_zyx=shp))
    # Amendment 10 §A10.2 overlay region (contract_io.overlay_region, as phase/tools/example_outputs.py): every scored
    # pair's evaluated points (PA, PB, midpoint) and every vertex the wrong-turn test evaluated, + 380 um, snapped to 128
    CIO = _contract_io(repo)
    ev_all, _ = _evaluated_points(args, {(r["patch_a"], r["patch_b"]) for r in scored}, feats_re, W, P, meta, use)
    tested = [pts[p][okp[p]] for p in allp if page_of.get(p) is not None]
    sets = ([ev_all[:, ::-1]] if len(ev_all) else []) + [t[:, ::-1] for t in tested if len(t)]
    oorg, oshp = CIO.overlay_region(sets, list(args.scan_shape)) if sets else (list(org), list(shp))  # item-159: the run's own scan (as SessA's 1efa92e3)
    head["overlay_region"] = dict(origin_zyx=[int(v) for v in oorg], shape_zyx=[int(v) for v in oshp], halo_um=380.0,
                                  rule="CONTRACT A10.2: bbox of scored pairs' PA/PB/midpoints and wrong-turn-tested vertices + halo, snapped to 128")
    _write_vertices(out / "vertices.csv", allp, pts, rc, K, th, page_of, maj, nref, okp, wrong, suspect, maxrisk)
    ov_info = (dict(skipped="--no-overlay") if getattr(args, "no_overlay", False) else _write_overlay(out, oorg, oshp, ev, pts, wrong, allp, args))
    cleaned = _write_cleaned(out, allp, G, where, rc, page_of, wrong, head)
    wraps = _write_wraps(out, allp, G, where, rc, page_of, wrong, K, th, s_hand, head) if solve_info else None
    _write_switch_risk(out / "switch_risk.csv", scored)
    if feats_re:
        _write_features(out / "recomputed_features.csv", feats_re)
    from . import p9filter
    p9 = p9filter.filter_rel(args.rel, out / "pipeline9", scored, thr, head, restrict=S)
    json.dump(dict(**head, frame="scan voxels zyx, 7.91 um",
                   wrap_index_source=("CONTRACT.md §2 solve on this region (wrap_index.csv)" if solve_info else "CONTRACT.md §2 (committed Q3c values)"),
                   format="vc_pointcollections_json v1", format_doc="phase/tools/SPIRAL_CONSTRAINTS.md",
                   note="CONTRACT Amendment 2: role files are SessE's; SessA writes the manifest with no constraints.",
                   constraints=[]), open(out / "spiral_constraints.json", "w"), indent=1)
    clusters = _clusters(ev, ev_pair, flagged, risk, pts, wrong, K, axis_xy, suspect)

    metrics = _metrics_block(M, repo, args, pl, E, area, th, tr, okp, allp, use)
    counts = dict(patches=len(allp), patches_with_wrap_index=sum(p in K for p in allp),
                  wrap_components=len({K[p][2] for p in allp if p in K}), joins=len(joins),
                  pairs_scored=len(scored), pairs_flagged=len(flagged),
                  pairs_flagged_contact=sum(1 for k in flagged if sep.get(k, 1e9) < 50),
                  pages=len(pl), wrong_turn_patches=sum(1 for p in allp if wrong[p].any()),
                  wrong_turn_points=int(sum(int(wrong[p].sum()) for p in allp)))
    n_sus = sum(int(suspect[p].sum()) for p in allp)
    areas = dict(patches_bbox=sum(area[p] for p in allp) / 100, pages=sum(area[p] for c in pl for p in c) / 100,
                 flagged_suspect=n_sus * CELL_MM2 / 100, wrong_turn=counts["wrong_turn_points"] * CELL_MM2 / 100,
                 cleaned_kept=cleaned["kept_cells"] * CELL_MM2 / 100)
    ru = resource.getrusage(resource.RUSAGE_SELF); rc_ = resource.getrusage(resource.RUSAGE_CHILDREN)
    axr = axis_xy.report() if isinstance(axis_xy, FLD.AxisFile) else None
    rep = dict(**head, status="ok", branch=branch, inputs=inputs, axis_file=axr, axis_queries_outside=(axr or {}).get("axis_queries_outside"), counts=counts, areas_cm2=areas, metrics=metrics, clusters=clusters,
               method=dict(flag_source=flag_source, blind_threshold=thr, page_min_mm2=args.page_min_mm2,
                           join_set="(iii-rf) from committed wrap index minus flagged joins",
                           rf_joins=len(rf), page_joins=len(E),
                           wrap_index=("solved from this region's witness (vc_sheet_check.solve)" if solve_info else "committed Q3c values (not re-solved)"),
                           solve=solve_info, wraps=wraps,
                           handedness_s=s_hand, axis=getattr(args, "axis_check", None), field=field_meta and {k: field_meta[k] for k in field_meta if k != "done"},
                           halo_l0=(field_meta or {}).get("halo_l0"), level=LEVEL, feature_comparison=feat_cmp,
                           overlay=ov_info, cleaned=cleaned, pipeline9=p9,
                           units="coordinates L0 voxels (z,y,x); areas cm2 (tifxyz cell = 4x4 voxels = 1.001e-3 mm2)"),
               resources=dict(wall_s=round(time.time() - t_start, 1), cpu_s=round(ru.ru_utime + ru.ru_stime + rc_.ru_utime + rc_.ru_stime, 1),
                              max_rss_mb=round(ru.ru_maxrss / 1024, 1), timing=timing))
    json.dump(rep, open(out / "report.json", "w"), indent=1, default=_js)
    if not args.keep_work:
        import shutil
        shutil.rmtree(cache, ignore_errors=True)
    return rep


def use_url(u, inputs):
    inputs[str(u)] = "remote (not hashed; chunk count and bytes are in method.field.pull)" if str(u).startswith("http") else "local"
    return u


def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def _contract_io(repo):
    import sys
    p = str(Path(repo) / "phase/tools")
    if p not in sys.path:
        sys.path.insert(0, p)
    import contract_io
    return contract_io


def _metrics(repo):
    import sys
    for p in (Path(repo) / "phase/tools", Path(repo) / "phase/h1"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import metrics as M
    return M


def _axis(repo, args, rows_all):
    """The scroll axis for the field orientation, theta and the solve's radial direction (SessA-7 rule, Amendment 2):
    --axis-file: that file. --axis x6: the contract §2 axis (refmesh.build_axis over X6's slab-2 node set, a full ring),
    only for a region inside that node set's centroid extent. No axis is ever derived from a region's own patch
    centroids (--axis table is refused): a set on one side of the scroll has its own centroid, not the scroll's, and
    no centroid test separates a compact patch from a ring (SessA-7). Otherwise exit 2: --axis-file required (as A5.3).
    Reported: the region's own centroids' largest angular gap about their Kasa circle centre (diagnostic only)."""
    diag = None
    if rows_all:
        C0 = np.array([[float(r["cx"]), float(r["cy"]), float(r["cz"])] for r in rows_all])
        cx, cy = kasa_centre(C0[:, :2]) if len(C0) >= 3 else (float("nan"), float("nan"))
        diag = dict(centroids=int(len(C0)), kasa_centre_xy=[round(cx, 1), round(cy, 1)],
                    largest_gap_deg_about_kasa_centre=round(axis_gap_deg(C0, lambda z: (np.full_like(z, cx), np.full_like(z, cy))), 1))
    if getattr(args, "axis_file", None):
        args.axis_check = dict(source="axis file", path=str(args.axis_file), region_centroid_diagnostic=diag)
        return FLD.load_axis_file(args.axis_file)
    from .segment import InputError
    if args.axis != "x6":
        raise InputError("--axis-file required: region mode does not derive the scroll axis from the region's own patch "
                         "centroids (SessA-7); --axis x6 is only for regions inside slab 2's X6 node set")
    from refmesh import build_axis
    x6rows = list(csv.DictReader(open(Path(repo) / "phase/x6/x6b_pairs.csv")))
    nodes = sorted({r["patch_a"] for r in x6rows} | {r["patch_b"] for r in x6rows}, key=int)
    ax, tab = build_axis(nodes, None)
    C = np.array([[float(tab[int(p)][c]) for c in ("cx", "cy", "cz")] for p in nodes])
    lo_n, hi_n = C.min(0)[::-1], C.max(0)[::-1]                      # z, y, x
    org = np.asarray(getattr(args, "origin", None) or lo_n); shp = np.asarray(getattr(args, "shape", None) or (hi_n - lo_n))
    inside = bool(np.all(org >= lo_n) and np.all(org + shp <= hi_n))
    scan = scan_id(getattr(args, "ct", None))
    args.axis_check = dict(source="refmesh.build_axis over X6's slab-2 node set (contract §2)", x6_centroid_extent_zyx=[lo_n.round(1).tolist(), hi_n.round(1).tolist()],
                           region_inside=inside, scan_id=scan, required_scan_id=SLAB2_SCAN_ID, region_centroid_diagnostic=diag)
    if scan != SLAB2_SCAN_ID:
        raise InputError(f"--axis-file required: the §2 axis belongs to scan {SLAB2_SCAN_ID} (PHerc1667); this CT's scan ID is "
                         f"{scan or 'unreadable'} (SessA-8)")
    if not inside:
        raise InputError("--axis-file required: the region is not inside slab 2's X6 node-set extent, where the §2 axis is defined (SessA-7)")
    return ax


AXIS_MAX_GAP_DEG = 90.0
SLAB2_SCAN_ID = "20231117161658"


def scan_id(ct_spec):
    """The scan's 14-digit ID: from the CT path/URL, else a local OME-Zarr's .zattrs multiscales[0].name (SessA-8)."""
    import re
    if not ct_spec:
        return None
    m = re.findall(r"(?<!\d)(\d{14})(?!\d)", str(ct_spec))
    if m:
        return m[-1]
    try:
        name = json.loads((Path(ct_spec) / ".zattrs").read_text())["multiscales"][0].get("name", "")
        m = re.findall(r"(?<!\d)(\d{14})(?!\d)", name)
        return m[-1] if m else None
    except Exception:
        return None


def axis_gap_deg(C, axis_xy):
    """Largest circular gap (degrees) between the angles of centroids C (x, y, z) about axis_xy(z)."""
    ax_, ay_ = axis_xy(C[:, 2])
    t = np.sort(np.mod(np.arctan2(C[:, 1] - ay_, C[:, 0] - ax_), 2 * np.pi))
    if len(t) < 2:
        return 360.0
    g = np.diff(np.r_[t, t[0] + 2 * np.pi])
    return float(np.degrees(g.max()))


def kasa_centre(xy):
    """Algebraic circle fit: minimise sum (|p - c|^2 - r^2)^2 linearised; returns the centre (x, y)."""
    A = np.c_[2 * xy, np.ones(len(xy))]; sol = np.linalg.lstsq(A, (xy ** 2).sum(1), rcond=None)[0]
    return float(sol[0]), float(sol[1])


def _axis_from_table(rows_all):
    from scipy.ndimage import uniform_filter1d
    c = np.array([[float(r["cx"]), float(r["cy"]), float(r["cz"])] for r in rows_all]); n = np.array([float(r["n"]) for r in rows_all])
    zb = np.arange(np.floor(c[:, 2].min() / 256) * 256, c[:, 2].max() + 256, 256)
    ax, ay = np.full(len(zb) - 1, np.nan), np.full(len(zb) - 1, np.nan)
    for i in range(len(zb) - 1):
        m = (c[:, 2] >= zb[i]) & (c[:, 2] < zb[i + 1])
        if m.any():
            ax[i] = np.average(c[m, 0], weights=n[m]); ay[i] = np.average(c[m, 1], weights=n[m])
    ok = np.isfinite(ax); zc = (zb[:-1] + zb[1:]) / 2
    ax = uniform_filter1d(np.interp(zc, zc[ok], ax[ok]), 3, mode="nearest"); ay = uniform_filter1d(np.interp(zc, zc[ok], ay[ok]), 3, mode="nearest")
    return lambda z: (np.interp(z, zc, ax), np.interp(z, zc, ay))


def _evaluated_points(args, flagged, feats_re, W, P, meta, use):
    """(N, 3) x,y,z evaluated points (PA, PB, midpoint) of flagged pairs, and each point's pair key."""
    if args.x6_points and args.x6_pairs:
        P6 = np.load(use(args.x6_points)); rows6 = list(csv.DictReader(open(use(args.x6_pairs))))
        keys = [jkey(r["patch_a"], r["patch_b"]) for r in rows6]
        m = np.array([keys[i] in flagged for i in P6["pair"]], bool) if len(P6["pair"]) else np.zeros(0, bool)
        A, B = P6["PA"][m], P6["PB"][m]; kk = [keys[i] for i in P6["pair"][m]]
    elif W is not None:
        ia = W["ia"]; pi = W["pi"]; keys = [jkey(*meta[q]) for q in range(len(meta))]
        m = np.array([keys[q] in flagged for q in pi], bool) if len(pi) else np.zeros(0, bool)
        A, B = P["PA"][ia][m], P["PB"][ia][m]; kk = [keys[q] for q in pi[m]]
    else:
        return np.zeros((0, 3)), []
    # midpoint in the stored dtype, then float64 (as phase/tools/example_outputs.py)
    return np.concatenate([A, B, (A + B) / 2]).astype(np.float64), kk * 3


def _write_vertices(path, allp, pts, rc, K, th, page_of, maj, nref, okp, wrong, suspect, maxrisk):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow("patch,row,col,z,y,x,wrap_index,theta,page,page_majority_n,n_ref,ref_ok,wrong_turn,suspect,max_risk".split(","))
        for p in allp:
            rr, cc = rc[p]; pg = page_of.get(p); k = K[p][0] if p in K else ""
            pm = maj.get(pg, "") if pg is not None else ""
            ok_ = okp[p] & (pg is not None)
            for q in range(len(rr)):
                x, y, z = pts[p][q]
                w.writerow([p, rr[q], cc[q], round(float(z), 2), round(float(y), 2), round(float(x), 2), k,
                            round(float(th[p][q]), 5), "" if pg is None else pg, pm,
                            int(nref[p][q]) if (pg is not None and ok_[q] and p in nref) else "", int(bool(ok_[q])),
                            int(bool(wrong[p][q])), int(bool(suspect[p][q])), round(maxrisk.get(p, 0.0), 6)])


def _raster(org, shp, ev, pts, wrong, allp):
    from scipy.ndimage import binary_dilation
    shp = np.array(shp); two = np.zeros(shp, bool)
    for p in allp:
        v = pts[p][wrong[p]]
        if len(v):
            idx = np.floor(v[:, ::-1]).astype(int) - org
            m = ((idx >= 0) & (idx < shp)).all(1); two[tuple(idx[m].T)] = True
    two = binary_dilation(two, iterations=1)
    one = np.zeros(shp, bool)
    for x, y, z in ev:
        c = np.array([z, y, x]) - org
        lo = np.maximum(np.floor(c - 3).astype(int), 0); hi = np.minimum(np.ceil(c + 3).astype(int) + 1, shp)
        if np.any(lo >= hi):
            continue
        g = np.stack(np.meshgrid(*[np.arange(a, b) for a, b in zip(lo, hi)], indexing="ij"), -1)
        one[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] |= np.linalg.norm(g + 0.5 - c, axis=-1) <= 3
    return np.maximum(one.astype(np.uint8), two.astype(np.uint8) * 2)


def _pyramid(a):
    levels = [a]
    while min(a.shape) >= 128:
        s = tuple((n // 2) * 2 for n in a.shape)
        a = a[:s[0], :s[1], :s[2]].reshape(s[0] // 2, 2, s[1] // 2, 2, s[2] // 2, 2).max((1, 3, 5)); levels.append(a)
    return levels


def _write_overlay(out, org, shp, ev, pts, wrong, allp, args):
    """overlay.zarr per CONTRACT Amendment 4 §A4.1: full-frame sparse OME-Zarr v2 over the scan's level shapes, no
    translation, only chunks inside the overlay region (A10.2; org/shp here), blosc-lz4. Written chunk by chunk (zarrio.write_overlay_fullframe_sparse,
    checked equal to phase/tools/contract_io.write_overlay_fullframe on fixture region A at all six levels)."""
    ov = _raster(np.array(org), shp, ev, pts, wrong, allp)
    scan = list(args.scan_shape)
    zarrio.write_overlay_fullframe_sparse(out / "overlay.zarr", zarrio.region_to_blocks(ov, org), scan, org, shp,
                                          name="vc_sheet_check overlay (contract v1 + A4)",
                                          extra_attrs=dict(values={"0": "none", "1": "suspect join", "2": "wrong-turn area"}))
    return dict(levels=6, voxels_1=int((ov == 1).sum()), voxels_2=int((ov == 2).sum()), format="Amendment 4 full-frame")


def _write_cleaned(out, allp, G, where, rc, page_of, wrong, head):
    import io
    import tifffile
    import zipfile
    kept_cells = removed = dropped = written = 0
    rows = []                                                             # cleaned_patches.csv (SessA-14): one row per patch
    for p in allp:
        pg = page_of.get(p)
        if pg is None:
            rows.append((p, "", 0, 0, 0, "no page (not in a page of >= page_min_mm2)")); continue
        src, mem, kind = where[p]
        if kind != "tifxyz":
            rows.append((p, pg, 0, 0, 0, f"not tifxyz ({kind})")); continue
        rd = (lambda n: zipfile.ZipFile(src).read(n)) if src.endswith(".zip") else (lambda n: open(Path(src) / n, "rb").read())
        raw = {c: rd(mem + c + ".tif") for c in "xyz"}
        arrs = {c: tifffile.imread(io.BytesIO(raw[c])).astype(np.float32).copy() for c in "xyz"}
        rr, cc = rc[p]; bad = wrong[p]
        if len(bad) and bad.mean() > 0.5:
            dropped += 1; rows.append((p, pg, 0, 0, int(bad.sum()), "dropped: > 50 % of its cells in a wrong-turn area")); continue
        d = out / "cleaned" / f"page_{pg:03d}" / f"patch_{p}"; d.mkdir(parents=True, exist_ok=True)
        for c in "xyz":
            arrs[c][rr[bad], cc[bad]] = -1; tifffile.imwrite(d / f"{c}.tif", arrs[c])
        try:
            meta = json.loads(rd(mem + "meta.json"))
        except Exception:
            meta = {"format": "tifxyz", "scale": [0.25, 0.25]}
        meta.update(contract="v1", git=head["git"], removed_cells=int(bad.sum()),
                    source_sha256={c: hashlib.sha256(raw[c]).hexdigest() for c in "xyz"})
        meta.setdefault("format", "tifxyz")
        json.dump(meta, open(d / "meta.json", "w"), indent=1)
        kept_cells += int(len(rr) - bad.sum()); removed += int(bad.sum()); written += 1
        rows.append((p, pg, 1, int(len(rr) - bad.sum()), int(bad.sum()), "kept" + (" (wrong-turn cells removed)" if bad.any() else "")))
    import csv as _csv
    with open(out / "cleaned_patches.csv", "w", newline="") as f:
        w = _csv.writer(f); w.writerow(["patch", "page", "kept", "cells_kept", "cells_removed", "reason"]); w.writerows(sorted(rows))
    return dict(patches_written=written, patches_dropped_over_50pct=dropped, removed_cells=removed, kept_cells=kept_cells)


def _write_switch_risk(path, scored):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patch_a", "patch_b", "risk", "flagged", "sep_um", "contact"])
        for r in scored:
            w.writerow([r["patch_a"], r["patch_b"], repr(float(r["risk"])), r["flagged"], r["sep_um"], int(r["sep_um"] < 50)])


def _write_features(path, feats):
    cols = ["patch_a", "patch_b", "verdict", "n_eval"] + FE.FEATURES + ["risk", "flagged"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(feats)


def _compare_features(feats_re, scored):
    """Recomputed (80 um field) vs committed features on common pairs: flag agreement."""
    c = {(r["patch_a"], r["patch_b"]): r for r in scored}
    common = [f for f in feats_re if (f["patch_a"], f["patch_b"]) in c]
    if not common:
        return dict(common_pairs=0)
    a = np.array([c[(f["patch_a"], f["patch_b"])]["flagged"] for f in common]); b = np.array([f["flagged"] for f in common])
    testable = np.array([f["n_testable"] > 0 for f in common])
    return dict(common_pairs=len(common), recomputed_only_pairs=len(feats_re) - len(common),
                committed_flagged=int(a.sum()), recomputed_flagged=int(b.sum()),
                both=int((a & b).sum()), committed_only=int((a & ~b).sum()), recomputed_only=int((~a & b).sum()),
                agreement=float((a == b).mean()), recomputed_testable_share=float(testable.mean()),
                note="committed features came from the slab-2 field at 118.67 um; recomputed use the fixed 80 um field")


def _clusters(ev, ev_pair, flagged, risk, pts, wrong, K, axis_xy, suspect):
    """§4.1: single linkage at 6.32 voxels over flagged pairs' evaluated points (suspect_join) and over
    wrong-turn points (wrong_turn)."""
    from scipy.spatial import cKDTree
    from refmesh import ang
    out = []
    def emit(kind, P, pairs_, patches_, area_cm2):
        z = P[:, ::-1]
        t = ang(P, axis_xy); tdeg = float(np.degrees(np.angle(np.mean(np.exp(1j * t)))) % 360)
        ks = [K[p][0] for p in patches_ if p in K]
        out.append(dict(id=len(out), kind=kind, n_pairs=len(pairs_), n_patches=len(patches_), area_cm2=area_cm2,
                        centroid_zyx=z.mean(0).round(2).tolist(), bbox_zyx=[z.min(0).round(2).tolist(), z.max(0).round(2).tolist()],
                        theta_deg=round(tdeg, 2), wrap_index_range=[min(ks), max(ks)] if ks else None,
                        patches=sorted(patches_), pairs=[list(k) for k in sorted(pairs_)],
                        max_risk=max([risk.get(k, 0.0) for k in pairs_], default=None)))
    if len(ev):
        units = sorted(set(ev_pair)); uid = {k: i for i, k in enumerate(units)}
        lab = _link(ev, np.array([uid[k] for k in ev_pair]), len(units))
        for L in np.unique(lab):
            pr = {units[i] for i in np.where(lab == L)[0]}
            m = np.array([k in pr for k in ev_pair]); pat = {q for k in pr for q in k}
            n_sus = sum(int(suspect[p].sum()) for p in pat if p in suspect)
            emit("suspect_join", ev[m], pr, pat, n_sus * CELL_MM2 / 100)
    W_ = [(p, pts[p][wrong[p]]) for p in sorted(pts) if wrong[p].any()]
    if W_:
        P = np.concatenate([v for _, v in W_]); owner = np.concatenate([np.full(len(v), i) for i, (p, v) in enumerate(W_)])
        lab = _link(P, owner, len(W_))
        for L in np.unique(lab):
            idx = np.where(lab == L)[0]; m = np.isin(owner, idx)
            emit("wrong_turn", P[m], set(), {W_[i][0] for i in idx}, int(m.sum()) * CELL_MM2 / 100)
    return out


def _link(P, owner, n_units):
    """Single linkage of units (pairs or patches): two units join when any of their points are within 6.32 voxels.
    Returns a component label per unit."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    pr = cKDTree(P).query_pairs(CLUSTER_VOX, output_type="ndarray")
    if len(pr):
        i, j = owner[pr[:, 0]], owner[pr[:, 1]]
    else:
        i = j = np.zeros(0, int)
    _, lab = connected_components(coo_matrix((np.ones(len(i)), (i, j)), shape=(n_units, n_units)), directed=False)
    return lab


def _metrics_block(M, repo, args, pl, E, area, th, tr, okp, allp, use):
    res = {}
    kr_path = Path(repo) / "phase/x7/X7_v9_patch_k.csv"
    v = {}
    if kr_path.exists():
        kr = {int(r["patch"]): r for r in csv.DictReader(open(kr_path))}
        t = {p: int(kr[p]["k_ref"]) + (float(kr[p]["theta_from_theta0"]) % M.TWO_PI) / M.TWO_PI for p in allp if p in kr and kr[p]["k_ref"] != ""}
        v["per_patch_layer"] = M.summarize(M.page_records(pl, E, area, *M.cross_per_patch_layer(t), t=t))
    else:
        v["per_patch_layer"] = None
    if args.x6_pairs:
        lab = M.load_x6_labels(args.x6_pairs)
        v["x6"] = M.summarize(M.page_records(pl, E, area, *M.cross_x6(lab)))
        if args.defects:
            defect = {M.jkey(r["patch_a"], r["patch_b"]): r["defect"] for r in csv.DictReader(open(use(args.defects)))}
            v["x6_excl"] = M.summarize(M.page_records(pl, E, area, *M.cross_x6(lab, defect)))
    if args.reference:
        v["m2_point"] = M.summarize_m2_point(M.m2_point_records(pl, E, th, tr, okp))
    else:
        v["m2_point"] = None; v["m2_point_reason"] = "no reference given (--reference); per-point M2 not computable"
    v["note"] = ("M1 cannot rank methods: every residual cross-turn join in every cleaned variant is a contact-regime join "
                 "where the reference is inconsistent (CONTRACT §5.2); the fixture is in-sample for the risk model (§6).")
    res["iii_rf_minus_flagged"] = v
    return res


def _write_axis_file(path, axis_xy, zmax):
    """Sample axis_xy every 8 L0 z (build_axis knots are at multiples of 128, so linear interpolation is exact)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    z = np.arange(0, int(zmax) + 8, 8, dtype=float); x, y = axis_xy(z)
    np.savetxt(path, np.stack([z, y, x], 1), delimiter=", ", fmt="%.6f")
    return path


def _solve(args, repo, out, P, meta, W, rows, G, allp, org, shp, use):
    """Region solve (contract §2): edges from this region's witness, spacing given or estimated, Q3c's LP."""
    from . import solve as SV
    from ._vendor import switchwitness_core as SW
    axis_xy = _axis(repo, args, rows)
    V, MED, AG, NT = SW.verdicts(W, len(meta))
    Ed, nodes, SA, SB, SI = SV.edges_from_witness(P, meta, W, MED, V, axis_xy, NT=NT, AG=AG, return_points=True)
    # label-free point export (SessA-14, as SessA-12): <= 10 witness points per non-coincident pair, X6's sampling rule
    np.savez(out / "points_labelfree.npz", PA=SA.astype(np.float32), PB=SB.astype(np.float32), edge=SI.astype(np.int32),
             edge_patches=np.array([[e["a"], e["b"]] for e in Ed], np.int64))
    tab = {int(r["id"]): r for r in rows}
    xyz = {p: np.array([float(tab[p][c]) for c in ("cx", "cy", "cz")]) for p in nodes}
    lo0 = np.asarray(org)[::-1]; hi0 = lo0 + np.asarray(shp)[::-1]
    vs = []
    for p in allp:
        g = G[p]; v = g[np.isfinite(g).all(-1) & (g[..., 0] > 0) & (g[..., 2] > 0)]
        vs.append(v[np.all((v >= lo0) & (v < hi0), 1)].astype(np.float32))
    verts = np.concatenate(vs) if vs else np.zeros((0, 3), np.float32)
    scan = SRC.CT(args.ct, LEVEL).shape0 or list(args.scan_shape)
    sp, est = SV.resolve_spacing(args.spacing_um, args.ct, verts, scan)
    st = SV.build_state(Ed, nodes, xyz, axis_xy, sp)
    res = SV.solve(st)
    axf = getattr(args, "axis_file", None) or _write_axis_file(out / "solve_axis_zyx.txt", axis_xy, scan[0])
    sub = verts[np.random.default_rng(1).choice(len(verts), min(2000, len(verts)), replace=False)] if len(verts) else None
    SV.save_edges(out / "solve_edges.json", Ed, nodes, xyz, axf, sub, dict(n_region_vertices=int(len(verts))))
    info = SV.write_wrap_index(out / "wrap_index.csv", st, res, dict(
        spacing_estimate=est, n_edges=len(Ed), n_d_i=sum(e["d_i"] is not None for e in Ed),
        n_d_ii=sum(e["d_ii"] is not None for e in st["E"]), n_stevens=sum(e["stevens"] for e in st["E"])))
    cmp = getattr(args, "compare_wrap_index", None)
    if cmp and Path(cmp).exists():
        Kr, Cr = SV.read_wrap_index(use(cmp))
        Kn = {p: int(round(res["k"][i])) for i, p in enumerate(st["nodes"])}
        info["compare_committed"] = dict(against=str(cmp), **SV.compare_up_to_component_constant(Kr, Cr, Kn))
        json.dump(info, open(out / "wrap_index.json", "w"), indent=1, default=_js)
    K = {p: (int(round(res["k"][i])), float(st["thN"][i]), str(int(res["component"][i]))) for i, p in enumerate(st["nodes"])}
    direct = {}
    for e in st["E"]:
        d = e["d_i"] if e["d_i"] is not None else e["d_ii"]
        if d is not None:
            direct[jkey(e["a"], e["b"])] = int(d)
    return K, res["s_chosen"], info, direct


def _write_wraps(out, allp, G, where, rc, page_of, wrong, K, th, s_hand, head):
    """tifxyz per wrap: every cleaned patch (on a page, <= 50 % wrong-turn) split by per-vertex wrap
    w = k_patch + s * cross(theta_patch, theta_vertex) (the solve's own cut convention), grouped by (component, w).
    Output wraps/c<component>_w<w>/patch_<id>/{x,y,z}.tif with other wraps' cells set to -1.
    Area per wrap: sum of kept cells, and the union after removing patch overlap (SessC's rule: unique 2-voxel cells x
    the wrap's own triangulated-area-per-cell ratio, here cells x (4 x 7.91 um)^2 / unique-cells-per-patch)."""
    import io
    import tifffile
    import zipfile
    from .solve import cross
    per = {}
    for p in allp:
        if p not in K or page_of.get(p) is None:
            continue
        src, mem, kind = where[p]
        if kind != "tifxyz":
            continue
        rr, cc = rc[p]; bad = wrong[p]
        if len(bad) and bad.mean() > 0.5:
            continue
        k, thN, comp = K[p]
        w = k + s_hand * cross(np.full(len(th[p]), thN), th[p])
        rd = (lambda n: zipfile.ZipFile(src).read(n)) if src.endswith(".zip") else (lambda n: open(Path(src) / n, "rb").read())
        arrs = {c: tifffile.imread(io.BytesIO(rd(mem + c + ".tif"))).astype(np.float32) for c in "xyz"}
        pts = G[p][rr, cc]
        for wv in np.unique(w[~bad]):
            m = (w == wv) & ~bad
            key = f"c{comp}_w{int(wv)}"
            d = out / "wraps" / key / f"patch_{p}"; d.mkdir(parents=True, exist_ok=True)
            for c in "xyz":
                a = np.full_like(arrs[c], -1); a[rr[m], cc[m]] = arrs[c][rr[m], cc[m]]; tifffile.imwrite(d / f"{c}.tif", a)
            json.dump(dict(format="tifxyz", scale=[0.25, 0.25], contract="v1", git=head["git"], component=comp, wrap=int(wv),
                           source_patch=int(p)), open(d / "meta.json", "w"))
            e = per.setdefault(key, dict(component=comp, wrap=int(wv), patches=0, cells=0, cells2=[]))
            e["patches"] += 1; e["cells"] += int(m.sum())
            e["cells2"].append(np.unique(np.floor(pts[m] / 2).astype(np.int64), axis=0))
    rows = []
    for key, e in sorted(per.items(), key=lambda kv: (kv[1]["component"], kv[1]["wrap"])):
        c2 = e.pop("cells2"); u = np.unique(np.concatenate(c2), axis=0); sum2 = sum(len(x) for x in c2)
        kr = e["cells"] * CELL_MM2 / max(sum2, 1)
        rows.append(dict(key=key, **e, area_sum_cm2=e["cells"] * CELL_MM2 / 100, area_union_cm2=len(u) * kr / 100))
    with open(out / "wraps" / "wraps.csv" if per else out / "wraps.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["key", "component", "wrap", "patches", "cells", "area_sum_cm2", "area_union_cm2"])
        wr.writeheader(); wr.writerows(rows)
    return dict(n_wraps=len(rows), rows=rows)
