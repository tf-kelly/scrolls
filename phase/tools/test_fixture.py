#!/usr/bin/env python3
"""Fixture tests for the integration contract (phase/tools/CONTRACT.md §6).

  python3 phase/tools/test_fixture.py                  # golden outputs reproduce from committed fixture files
  python3 phase/tools/test_fixture.py --outputs DIR    # also validate a run's §4 outputs in DIR against the contract
                                                       # and against the golden values the contract fixes
  ... --outputs DIR --pre-a10                          # Amendment 10 checks (overlay_region) reported as PENDING,
                                                       # not failed: for a branch merged before it adopts A10.2

Golden checks (no network, no bulk data):
  G1 provenance: every patch member in patches.zip matches its recorded SHA-256; CT level 0 matches its hash.
  SessC wrap index: golden/wrap_index.csv equals phase/p1page/p1b_q3c_k.csv on the fixture patches.
  G3 switch risk: risk_model_v1 on pair_features.csv reproduces golden/switch_risk.csv exactly (risk and flag).
  G4 pages: metrics.py on the fixture's rel.csv / X6 labels / reference subset reproduces golden/pages_metrics.json.
  G7 solve: the wrap-index solver (OR-Tools) runs on the fixture's joins and reproduces the golden differences.
"""
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

T = Path(__file__).resolve().parent; R = T.parents[1]; F = R / "phase/data_small/fixture"
sys.path.insert(0, str(T)); sys.path.insert(0, str(R / "phase/h1"))
import metrics as M  # noqa: E402

FAIL = []
sha = lambda b: hashlib.sha256(b).hexdigest()


PRE_A10 = "--pre-a10" in sys.argv
PENDING = []


def ok(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}{(': ' + str(detail)) if detail else ''}")
    if not cond:
        FAIL.append(name)


def ok_a10(name, cond, detail=""):
    """Amendment 10 check: a failure is PENDING (not FAIL) only under --pre-a10."""
    if PRE_A10 and not cond:
        print(f"PENDING (A10)  {name}{(': ' + str(detail)) if detail else ''}"); PENDING.append(name)
    else:
        ok(name, cond, detail)


def fnum(x):
    return float("nan") if x in ("", None, "nan") else float(x)


def load_fixture():
    prov = json.load(open(F / "provenance.json"))
    pc = {int(r["id"]): r for r in csv.DictReader(open(F / "patches.csv"))}
    return prov, pc


def patch_points(pc):
    import tifffile
    pts = {}
    with zipfile.ZipFile(F / "patches.zip") as z:
        for p, r in pc.items():
            base = f"s4_{r['label']}_patches/patch_{p}/"
            X, Y, Z = (tifffile.imread(io.BytesIO(z.read(base + c + ".tif"))) for c in "xyz")
            m = np.isfinite(X) & (X > 0) & np.isfinite(Z) & (Z > 0)
            pts[p] = np.column_stack([X[m], Y[m], Z[m]]).astype(np.float64)
    return pts


def golden():
    prov, pc = load_fixture(); allp = sorted(pc)
    # G1
    with zipfile.ZipFile(F / "patches.zip") as z:
        bad = [n for n, h in prov["patch_members_sha256"].items() if sha(z.read(n)) != h]
    ok("G1 patch members match recorded SHA-256", not bad and len(prov["patch_members_sha256"]) == 4 * len(allp), f"{len(bad)} mismatched")
    if (F / "ct.zarr").exists():
        import zarr
        a = zarr.open_array(str(F / "ct.zarr/0"), mode="r")[...]
        ok("G1 CT level 0 hash", sha(np.ascontiguousarray(a, "<u2").tobytes()) == prov["ct"]["level0_sha256"])
        ok("G1 CT chunking = scan (128³, uint16)", a.dtype == np.dtype("<u2") and zarr.open_array(str(F / "ct.zarr/0"), mode="r").chunks == (128, 128, 128))
    # SessC
    kq = {int(r["patch"]): r for r in csv.DictReader(open(R / "phase/p1page/p1b_q3c_k.csv"))}
    g = list(csv.DictReader(open(F / "golden/wrap_index.csv")))
    ok("SessC wrap index = p1b_q3c_k.csv", all(r["wrap_index"] == kq[int(r["patch"])]["k_q3c"] and r["theta"] == kq[int(r["patch"])]["thN"] for r in g), f"{len(g)} patches")
    # G3
    import joblib
    mdl = joblib.load(R / "phase/tools/risk_model/risk_model_v1.joblib")
    feats = list(csv.DictReader(open(F / "pair_features.csv")))
    p = mdl["model"].predict_proba(np.array([[fnum(r[c]) for c in mdl["active_features"]] for r in feats]))[:, 1]
    gs = list(csv.DictReader(open(F / "golden/switch_risk.csv")))
    ok("G3 switch risk reproduces exactly", len(gs) == len(p) and all(float(r["risk"]) == float(x) and int(r["flagged"]) == int(x >= mdl["threshold"]) for r, x in zip(gs, p)),
       f"{len(gs)} pairs, {sum(int(r['flagged']) for r in gs)} flagged, threshold {mdl['threshold']}")
    meta = json.load(open(R / "phase/tools/risk_model/risk_model_v1.json"))
    ok("G3 risk model file hash", sha((R / "phase/tools/risk_model/risk_model_v1.joblib").read_bytes()) == meta["model_sha256"])
    # G4
    from refmesh import ang, build_axis
    x6rows_all = list(csv.DictReader(open(R / "phase/x6/x6b_pairs.csv")))
    nodes = sorted({r["patch_a"] for r in x6rows_all} | {r["patch_b"] for r in x6rows_all}, key=int)
    axis_xy, _ = build_axis(nodes, None)
    area = M.bbox_area_mm2(F / "patches.csv")
    kr = {int(r["patch"]): r for r in csv.DictReader(open(R / "phase/x7/X7_v9_patch_k.csv"))}
    t = {p: int(kr[p]["k_ref"]) + (float(kr[p]["theta_from_theta0"]) % M.TWO_PI) / M.TWO_PI for p in allp if p in kr and kr[p]["k_ref"] != ""}
    x6lab = M.load_x6_labels(F / "x6_pairs.csv")
    flip1 = {M.jkey(*r[:2]) for r in csv.reader(open(R / "phase/x10/flip1_pairs.csv"))}
    joins = sorted({M.jkey(*r[:2]) for r in csv.reader(open(F / "rel.csv"))} - flip1)
    bad9 = {int(x) for x in open(F / "pipeline9_badpatches_b.csv").read().split()}
    rf = {tuple(k) for k in json.load(open(R / "phase/p1page/p1b_rf_joins.json"))["kept"]}
    V = {"i_all": joins, "ii_pipeline9_deletions": [k for k in joins if k[0] not in bad9 and k[1] not in bad9], "iii_rf": [k for k in joins if k in rf]}
    from scipy.spatial import cKDTree
    RS = np.load(F / "reference_subset.npz"); tree = cKDTree(RS["xyz"].astype(np.float64)); RT = RS["t_ref"].astype(np.float64)
    pts = patch_points(pc); th, tr, okp = {}, {}, {}
    for p in allp:
        d, j = tree.query(pts[p], distance_upper_bound=60 / M.VOX_UM); m = np.isfinite(d)
        tt = np.full(len(d), np.nan); tt[m] = RT[j[m]]; th[p] = ang(pts[p], axis_xy); tr[p] = tt; okp[p] = m
    G = json.load(open(F / "golden/pages_metrics.json")); g_min = G["i_all"]["page_min_mm2"]
    defect = {M.jkey(r["patch_a"], r["patch_b"]): r["defect"] for r in csv.DictReader(open(F / "golden/defects.csv"))}
    mids = M.join_midpoints(F / "x6_points.npz", [(int(r["patch_a"]), int(r["patch_b"])) for r in csv.DictReader(open(F / "x6_pairs.csv"))])
    ok("G4 defect test reproduces golden/defects.csv", all(M.defect_at(mids[k], tree, RS["u"].astype(np.float64), RS["xyz"].astype(np.float64)) == v for k, v in defect.items()),
       {s_: sum(v == s_ for v in defect.values()) for s_ in ("ok", "duplicated", "displaced")})
    for name, E in V.items():
        pl = M.pages(E, allp, area, g_min)
        a = M.summarize(M.page_records(pl, E, area, *M.cross_per_patch_layer(t), t=t))
        b = M.summarize(M.page_records(pl, E, area, *M.cross_x6(x6lab)))
        e = M.summarize(M.page_records(pl, E, area, *M.cross_x6(x6lab, defect)))
        c = M.summarize_m2_point(M.m2_point_records(pl, E, th, tr, okp))
        g = G[name]
        same = lambda u, v: all((u[k] is None and v[k] is None) or abs(float(u[k]) - float(v[k])) <= 1e-9 * max(1, abs(float(v[k]))) for k in v)
        ok(f"G4 {name} pages", [list(x) for x in pl] == g["pages"], f"{len(pl)} pages")
        ok(f"G4 {name} per-patch-layer M1/M2/M3", same(a, g["per_patch_layer"]), f"M1 {a['M1']:.4f} M2_patch {a['M2_patch']}")
        ok(f"G4 {name} X6 M1/M3", same(b, g["x6"]), f"M1 {b['M1']:.4f} excluded {b['excluded_joins']}/{b['page_joins']}")
        ok(f"G4 {name} X6-excl M1/M3", same(e, g["x6_excl"]), f"M1 {e['M1']:.4f}")
        ok(f"G4 {name} M2 per point", same(c, g["m2_point"]), f"M2_point {c['M2_point']} excluded pts {c['excluded_points']}")


def golden_v1_1():
    """G5 (fixture v1.1): expected X6 cross-turn clusters reproduce; golden report has >= 3 expected clusters' worth of
    X6-confirmed cross-turn joins and non-empty clusters."""
    sys.path.insert(0, str(F)); import build_golden_v1_1 as BG
    e = BG.expected_clusters(); g = json.load(open(F / "golden/expected_cross_turn_clusters.json"))
    ok("G5 expected X6 cross-turn clusters reproduce", json.loads(json.dumps(e)) == g, f"{g['n_joins']} joins, {len(g['clusters'])} clusters")
    ok("G5 fixture has >= 3 X6-confirmed cross-turn joins", g["n_joins"] >= 3)
    rep = json.load(open(F / "golden/report.json"))
    ok("G5 golden report has clusters of both kinds", {c["kind"] for c in rep["clusters"]} == {"suspect_join", "wrong_turn"}, len(rep["clusters"]))


# ------------------------------------------------------------------------------------------ §4 output validation

def validate_outputs(out):
    out = Path(out)
    rep = json.load(open(out / "report.json"))
    for k in ("contract", "git", "branch", "region", "inputs", "counts", "areas_cm2", "metrics", "clusters"):
        ok(f"report.json has {k}", k in rep)
    ok("report.json contract v1", rep.get("contract") == "v1")
    for k in ("patches", "patches_with_wrap_index", "wrap_components", "joins", "pairs_scored", "pairs_flagged", "pairs_flagged_contact", "pages", "wrong_turn_patches", "wrong_turn_points"):
        ok(f"counts.{k} int", isinstance(rep.get("counts", {}).get(k), int))
    for c in rep.get("clusters", []):
        ok(f"cluster {c.get('id')} fields", all(k in c for k in ("id", "kind", "n_pairs", "n_patches", "area_cm2", "centroid_zyx", "bbox_zyx", "theta_deg", "wrap_index_range", "patches", "pairs", "max_risk")) and c["kind"] in ("suspect_join", "wrong_turn"))
    # overlay: Amendment 4 §A4.1 (full-frame sparse OME-Zarr v2, no translation)
    import contract_io as CIO
    ok("report.json status ok", rep.get("status") == "ok")
    ov = out / "overlay.zarr"
    ok("overlay is Zarr v2 on disk", (ov / ".zgroup").exists() and json.load(open(ov / ".zgroup")).get("zarr_format") == 2)
    ms = json.load(open(ov / ".zattrs"))["multiscales"][0]
    ok("overlay axes z,y,x", [a["name"] for a in ms.get("axes", [])] == ["z", "y", "x"])
    # Amendment 10 §A10.2: the written overlay region is report.json `overlay_region`; before A10 it was `region`
    has_or = "overlay_region" in rep
    ok_a10("report.json has overlay_region (A10.2)", has_or)
    orr = rep["overlay_region"] if has_or else rep["region"]
    org = orr["origin_zyx"]; shp = orr["shape_zyx"]
    ok("overlay region origin chunk-aligned", all(o % 128 == 0 for o in org))
    mj = json.load(open(ov / "meta.json")) if (ov / "meta.json").exists() else {}
    ok("overlay meta.json (VC3D)", mj.get("type") == "vol" and [mj.get("slices"), mj.get("height"), mj.get("width")] == list(CIO.SCAN_LEVEL_SHAPES[0]) and abs(float(mj.get("voxelsize", 0)) - 7.91) < 1e-9)
    ok("overlay has levels 0..5", [d["path"] for d in ms.get("datasets", [])] == [str(l) for l in range(6)])
    import zarr
    prev = None
    for lv, ds in enumerate(ms.get("datasets", [])):
        za = json.load(open(ov / ds["path"] / ".zarray"))
        tr = [t for t in ds["coordinateTransformations"] if t["type"] == "translation"]
        sc = [t for t in ds["coordinateTransformations"] if t["type"] == "scale"][0]["scale"]
        ok(f"overlay L{lv} no translation, scale 7.91*2^l", all(v == 0 for t in tr for v in t["translation"]) and np.allclose(sc, [7.91 * 2 ** lv] * 3))
        ok(f"overlay L{lv} full-frame shape, 128³, u1, fill 0, '/', blosc-lz4",
           za["zarr_format"] == 2 and tuple(za["shape"]) == CIO.SCAN_LEVEL_SHAPES[lv] and za["chunks"] == [128] * 3 and za["dtype"] in ("|u1", "uint8")
           and za["fill_value"] == 0 and za.get("dimension_separator") == "/" and (za.get("compressor") or {}).get("cname") == "lz4")
        lo = [o >> lv for o in org]; hi = [-(-(o + s_) // 2 ** lv) for o, s_ in zip(org, shp)]
        clo = [l // 128 for l in lo]; chi = [-(-h // 128) for h in hi]
        keys = [k.relative_to(ov / ds["path"]).parts for k in (ov / ds["path"]).rglob("*") if k.is_file() and not k.name.startswith(".")]
        ok(f"overlay L{lv} stores only chunks inside the snapped region", all(clo[i] <= int(k[i]) < chi[i] for k in keys for i in range(3)), f"{len(keys)} chunks")
        a = zarr.open_array(str(ov / ds["path"]), mode="r")
        v = a[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
        ok(f"overlay L{lv} values in {{0,1,2}}", set(np.unique(v).tolist()) <= {0, 1, 2})
        if prev is not None:
            pv, plo = CIO._pool(prev[0], prev[1])
            d0 = [l - q for l, q in zip(lo, plo)]
            sub = pv[d0[0]:d0[0] + v.shape[0], d0[1]:d0[1] + v.shape[1], d0[2]:d0[2] + v.shape[2]]
            ok(f"overlay L{lv} is 2x max-pool of L{lv - 1}", sub.shape == v.shape and np.array_equal(sub, v))
        if lv == 0:
            L0 = (v, lo)
        prev = (v, lo)
    outside, unflagged = [], []
    for c in rep.get("clusters", []):
        cz, bb = c["centroid_zyx"], c["bbox_zyx"]
        ok(f"cluster {c['id']} zyx inside scan, centroid inside bbox", all(0 <= cz[i] < CIO.SCAN_LEVEL_SHAPES[0][i] for i in range(3)) and all(bb[0][i] <= cz[i] <= bb[1][i] for i in range(3)))
        if not all(org[i] <= cz[i] < org[i] + shp[i] for i in range(3)):
            outside.append(c["id"])
        # a jump to the cluster must land where the overlay shows its flag: some voxel of its kind's value in its bbox
        v0, lo0 = L0; want = 1 if c["kind"] == "suspect_join" else 2
        a_ = [max(int(np.floor(bb[0][i])) - lo0[i], 0) for i in range(3)]; b_ = [min(int(np.ceil(bb[1][i])) + 1 - lo0[i], v0.shape[i]) for i in range(3)]
        if any(x >= y for x, y in zip(a_, b_)) or not np.any(v0[a_[0]:b_[0], a_[1]:b_[1], a_[2]:b_[2]] == want):
            unflagged.append(c["id"])
    ok_a10("every cluster centre inside the written overlay region (A10.2)", not outside, f"{len(outside)} outside: {outside[:8]}")
    ok_a10("every cluster's bbox holds a voxel of its overlay value (A10.2)", not unflagged, f"{len(unflagged)} without: {unflagged[:8]}")
    # Amendment 8 §A8.1: segment-mode reports carry a power statement and label
    if str(rep.get("method", {}).get("mode", "")).startswith("segment"):
        pw = rep.get("power") or {}
        ok("segment mode: power block present (A8.1)", all(k in pw for k in ("decision_rule", "pairs_per_cm2", "testable_share",
                                                                        "testable_neighbours_within_eps", "power", "label")))
        low = pw.get("power") is None or pw.get("power") < 0.5
        ok("segment mode: label 'not a clean-segment test' when power < 0.5 or null", (not low) or pw.get("label") == "not a clean-segment test")
    # Amendment 5 §A5.5: a run on fixture region A must reproduce the golden §4.1 clusters and join count
    g = json.load(open(F / "golden/report.json"))
    if rep["region"] == g["region"]:
        key = lambda c: (c["kind"], tuple(tuple(p) for p in c["pairs"]) if c["kind"] == "suspect_join" else tuple(c["patches"]))
        mine_c, gold_c = sorted(map(key, rep.get("clusters", []))), sorted(map(key, g["clusters"]))
        ok("region A: clusters equal golden (pairs per suspect join, patches per wrong turn)", mine_c == gold_c,
           f"{len(mine_c)} vs golden {len(gold_c)}")
        gk = {key(c): c for c in g["clusters"]}; fbad = []
        for c in rep.get("clusters", []):
            d = gk.get(key(c))
            if d is None:
                continue
            for f in d:
                if f == "id":
                    continue
                a, b = c.get(f), d[f]
                good = (abs(a - b) <= 0.01) if f == "theta_deg" and a is not None else \
                    (abs(a - b) <= 1e-9 * max(1, abs(b))) if isinstance(a, float) and isinstance(b, float) else a == b
                if not good:
                    fbad.append((c["kind"], f))
        ok("region A: cluster fields equal golden (Amendment 7 §A7.2; theta to 0.01 deg)", not fbad, fbad[:5])
        ok("region A: counts and areas_cm2 equal golden", rep["counts"] == g["counts"] and
           all(abs((rep["areas_cm2"].get(k) or 0) - (v or 0)) <= 1e-9 for k, v in g["areas_cm2"].items()))
        gor = {k: g["overlay_region"][k] for k in ("origin_zyx", "shape_zyx")}
        ror = {k: (rep.get("overlay_region") or {}).get(k) for k in ("origin_zyx", "shape_zyx")}
        ok_a10("region A: overlay_region equals golden v1.4 (A10.2)", ror == gor, f"{ror} vs {gor}")
        ok("region A: counts.joins equals golden (Amendment 5 §A5.4)", rep["counts"].get("joins") == g["counts"]["joins"],
           f"{rep['counts'].get('joins')} vs {g['counts']['joins']}")
    # vertices.csv
    cols = "patch,row,col,z,y,x,wrap_index,theta,page,page_majority_n,n_ref,ref_ok,wrong_turn,suspect,max_risk".split(",")
    with open(out / "vertices.csv") as f:
        hdr = next(csv.reader(f))
    ok("vertices.csv columns", hdr == cols, hdr)
    # cleaned tifxyz
    metas = list((out / "cleaned").glob("*/patch_*/meta.json"))
    ok("cleaned tifxyz present", len(metas) > 0, f"{len(metas)} patches")
    for mp in metas[:10]:
        m = json.load(open(mp))
        ok(f"{mp.parent.name} meta", m.get("contract") == "v1" and m.get("format") == "tifxyz" and "source_sha256" in m and "removed_cells" in m and all((mp.parent / f"{c}.tif").exists() for c in "xyz"))
    # spiral constraints envelope
    sc = json.load(open(out / "spiral_constraints.json"))
    ok("spiral_constraints envelope", all(k in sc for k in ("contract", "git", "region", "frame", "wrap_index_source", "format", "format_doc", "constraints")))
    # Amendment 2: VC3D point-collection role files, if written
    for fn in ("abs_winding.json", "relative_windings.json", "same_windings.json"):
        fp = out / "spiral" / fn
        if not fp.exists():
            continue
        d = json.load(open(fp)); good = d.get("vc_pointcollections_json_version") == "1" and isinstance(d.get("collections"), dict)
        for cid, col in (d.get("collections") or {}).items():
            for pid, pt in col.get("points", {}).items():
                good &= len(pt.get("p", [])) == 3 and all(isinstance(v, (int, float)) for v in pt["p"]) and isinstance(pt.get("wind_a", 0.0), (int, float))
                good &= "hard" not in pt and "weight" not in pt
            if fn == "relative_windings.json":
                good &= len(col.get("points", {})) == 2 and col.get("name", "").startswith("between_patches__")
        ok(f"spiral/{fn} schema (A2.2; 2-point between_patches collections for relative)", good)
        ok(f"spiral/{fn} listed in manifest", any(fn in json.dumps(c) for c in sc.get("constraints", [])))
    # pipeline9
    for fn in ("rel_filtered.csv", "removed_joins.csv", "filter.json"):
        ok(f"pipeline9/{fn}", (out / "pipeline9" / fn).exists())
    # golden values the contract fixes, when the run is on the fixture with the committed features
    gs = {M.jkey(r["patch_a"], r["patch_b"]): int(r["flagged"]) for r in csv.DictReader(open(F / "golden/switch_risk.csv"))}
    if (out / "switch_risk.csv").exists():
        mine = {M.jkey(r["patch_a"], r["patch_b"]): int(r["flagged"]) for r in csv.DictReader(open(out / "switch_risk.csv"))}
        common = set(mine) & set(gs)
        ok("flags equal golden on common pairs", all(mine[k] == gs[k] for k in common), f"{len(common)} common pairs")
    if (out / "vertices.csv").exists():
        gw = {int(r["patch"]): (int(r["wrap_index"]), r["component"]) for r in csv.DictReader(open(F / "golden/wrap_index.csv"))}
        seen = {}
        for r in csv.DictReader(open(out / "vertices.csv")):
            p = int(r["patch"])
            if p in gw and r["wrap_index"] != "" and p not in seen:
                seen[p] = int(r["wrap_index"]) - gw[p][0]
        offs = {}
        for p, d in seen.items():
            offs.setdefault(gw[p][1], set()).add(d)
        ok("wrap index = golden up to one constant per component", all(len(v) == 1 for v in offs.values()), {k: sorted(v)[:5] for k, v in offs.items()})


def axis_formats():
    """G6 (Amendment 12 §A12.1): contract_io reads the axis file in our CSV and in villa's umbilicus.json identically."""
    import tempfile
    import contract_io as CIO
    with tempfile.TemporaryDirectory() as d:
        ok("G6 axis file: CSV and villa umbilicus.json read identically", CIO._selftest_axis(d))


def solve_runs():
    """G7 (coordinator 20:45; the cold quickstart caught that no test exercised the solve): the wrap-index solver
    (vc_sheet_check.circulation, OR-Tools min-cost flow) runs on the fixture's joins. Terms built from the golden wrap
    index on every fixture pair in one component are consistent, so the optimum must be 0 and reproduce every golden
    difference; one contradicting weight-1 term per 10 pairs (against weight-3 consistent terms) must be outvoted and
    counted in the objective. A missing solver dependency fails here, not later in the quickstart."""
    sys.path.insert(0, str(T / "vc_sheet_check"))
    from vc_sheet_check import circulation as CIRC
    g = {int(r["patch"]): r for r in csv.DictReader(open(F / "golden/wrap_index.csv"))}
    pairs = [(int(r["patch_a"]), int(r["patch_b"])) for r in csv.DictReader(open(F / "pair_features.csv"))]
    pairs = [(a, b) for a, b in pairs if a in g and b in g and g[a]["component"] == g[b]["component"]]
    ids = sorted({p for ab in pairs for p in ab}); pos = {p: i for i, p in enumerate(ids)}
    kd = lambda a, b: int(g[b]["wrap_index"]) - int(g[a]["wrap_index"])
    terms = [(pos[a], pos[b], kd(a, b), 1) for a, b in pairs]
    k, _, obj = CIRC.solve_plain(terms, len(ids))
    ok("G7 solver runs on the fixture's joins; consistent terms give objective 0", obj == 0 and len(terms) > 0, f"{len(terms)} terms, {len(ids)} patches")
    ok("G7 solved differences equal the golden wrap index on every term", all(int(k[pos[b]] - k[pos[a]]) == kd(a, b) for a, b in pairs))
    bad = pairs[::10]
    terms2 = [(pos[a], pos[b], kd(a, b), 3) for a, b in pairs] + [(pos[a], pos[b], kd(a, b) + 1, 1) for a, b in bad]
    k2, _, obj2 = CIRC.solve_plain(terms2, len(ids))
    ok("G7 contradicting terms are outvoted and counted", obj2 == len(bad) and all(int(k2[pos[b]] - k2[pos[a]]) == kd(a, b) for a, b in pairs),
       f"objective {obj2}, {len(bad)} contradicting terms")


if __name__ == "__main__":
    golden()
    golden_v1_1()
    axis_formats()
    solve_runs()
    if "--outputs" in sys.argv:
        validate_outputs(sys.argv[sys.argv.index("--outputs") + 1])
    if PENDING:
        print(f"\nPENDING (Amendment 10, --pre-a10): {PENDING}")
    print("\nALL PASS" if not FAIL else f"\nFAILED: {FAIL}")
    raise SystemExit(0 if not FAIL else 1)
