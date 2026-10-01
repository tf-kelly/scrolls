#!/usr/bin/env python3
"""Minimal reference writer for the contract's §4 outputs on fixture region A, built from the golden values.

It exists to prove that §4 can be implemented and that `test_fixture.py --outputs` accepts a correct run. It is
not a method: every flag and wrap number is copied from golden/, cleaning is the §4.4 rule applied to §5.4 minority
points, and the spiral-constraints list is empty (SessE defines the records).
Usage: python3 phase/tools/example_outputs.py OUT_DIR"""
import csv
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np

T = Path(__file__).resolve().parent; R = T.parents[1]; F = R / "phase/data_small/fixture"
sys.path.insert(0, str(T)); sys.path.insert(0, str(R / "phase/h1"))
import metrics as M  # noqa: E402
import test_fixture as TF  # noqa: E402
import contract_io as CIO  # noqa: E402


def main(out):
    import tifffile
    from scipy.ndimage import binary_dilation, maximum_filter
    from scipy.spatial import cKDTree
    from refmesh import ang, build_axis
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    prov, pc = TF.load_fixture(); reg = prov["regions"]["A_rich"]
    org = [reg["z"][0], reg["y"][0], reg["x"][0]]; shp = [reg[a][1] - reg[a][0] for a in "zyx"]
    allp = sorted(p for p, r in pc.items() if "A_rich" in r["regions"].split("|"))
    S = set(allp); git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=R).stdout.strip()
    head = dict(contract="v1", amendments=[2, 3, 4, 10], status="ok", git=git, region=dict(origin_zyx=org, shape_zyx=shp))
    pts = {p: v for p, v in TF.patch_points(pc).items() if p in S}
    wrap = {int(r["patch"]): (int(r["wrap_index"]), r["component"], float(r["theta"])) for r in csv.DictReader(open(F / "golden/wrap_index.csv"))}
    risk = [r for r in csv.DictReader(open(F / "golden/switch_risk.csv")) if int(r["patch_a"]) in S and int(r["patch_b"]) in S]
    sep = {M.jkey(r["patch_a"], r["patch_b"]): float(r["sep_um"]) for r in csv.DictReader(open(F / "pair_features.csv"))}
    flagged = {M.jkey(r["patch_a"], r["patch_b"]) for r in risk if r["flagged"] == "1"}
    maxrisk = {}
    for r in risk:
        for p in (int(r["patch_a"]), int(r["patch_b"])):
            maxrisk[p] = max(maxrisk.get(p, 0.0), float(r["risk"]))
    # pages: (iii-rf) joins minus flagged joins, fixture page threshold
    G = json.load(open(F / "golden/pages_metrics.json")); gmin = G["iii_rf"]["page_min_mm2"]
    flip1 = {M.jkey(*r[:2]) for r in csv.reader(open(R / "phase/x10/flip1_pairs.csv"))}
    rf = {tuple(k) for k in json.load(open(R / "phase/p1page/p1b_rf_joins.json"))["kept"]}
    E = [k for k in sorted({M.jkey(*r[:2]) for r in csv.reader(open(F / "rel.csv"))} - flip1) if k in rf and k[0] in S and k[1] in S and k not in flagged]
    area = M.bbox_area_mm2(F / "patches.csv"); pl = M.pages(E, allp, area, gmin); page_of = {p: i for i, c in enumerate(pl) for p in c}
    x6rows = list(csv.DictReader(open(R / "phase/x6/x6b_pairs.csv")))
    axis_xy, _ = build_axis(sorted({r["patch_a"] for r in x6rows} | {r["patch_b"] for r in x6rows}, key=int), None)
    RS = np.load(F / "reference_subset.npz"); tree = cKDTree(RS["xyz"].astype(np.float64)); RT = RS["t_ref"].astype(np.float64)
    th, tr, okp = {}, {}, {}
    for p in allp:
        d, j = tree.query(pts[p], distance_upper_bound=60 / M.VOX_UM); m = np.isfinite(d)
        tt = np.full(len(d), np.nan); tt[m] = RT[j[m]]; th[p] = ang(pts[p], axis_xy); tr[p] = tt; okp[p] = m
    # per-point n in page frame (same formula as metrics.m2_point_records)
    nref, maj = {}, {}
    for i, c in enumerate(pl):
        tmed = {p: float(np.angle(np.mean(np.exp(1j * th[p])))) % M.TWO_PI for p in c}; off = M.unwrap_page_theta(c, E, tmed)
        allv = []
        for p in c:
            thu = tmed[p] + (np.mod(th[p] - tmed[p] + np.pi, M.TWO_PI) - np.pi) + off[p]
            n = np.full(len(th[p]), np.iinfo(np.int64).min); n[okp[p]] = np.round(tr[p][okp[p]] - thu[okp[p]] / M.TWO_PI).astype(int)
            nref[p] = n; allv.append(n[okp[p]])
        v, cnt = np.unique(np.concatenate(allv), return_counts=True); maj[i] = int(v[np.argmax(cnt)])
    # evaluated points of flagged pairs
    P6 = np.load(F / "x6_points.npz"); rows6 = list(csv.DictReader(open(F / "x6_pairs.csv")))
    fl_idx = [i for i, r in enumerate(rows6) if M.jkey(r["patch_a"], r["patch_b"]) in flagged]
    m6 = np.isin(P6["pair"], fl_idx)
    ev = np.concatenate([P6["PA"][m6], P6["PB"][m6], (P6["PA"][m6] + P6["PB"][m6]) / 2]).astype(np.float64)   # (x,y,z)
    evtree = cKDTree(ev) if len(ev) else None
    # Amendment 10 §A10.2 overlay region: every scored pair's evaluated points + every vertex the wrong-turn test evaluated
    scored = {M.jkey(r["patch_a"], r["patch_b"]) for r in risk}
    ms = np.isin(P6["pair"], [i for i, r in enumerate(rows6) if M.jkey(r["patch_a"], r["patch_b"]) in scored])
    ev_all = np.concatenate([P6["PA"][ms], P6["PB"][ms], (P6["PA"][ms] + P6["PB"][ms]) / 2]).astype(np.float64)
    tested = [pts[p][okp[p]] for p in allp if page_of.get(p) is not None]
    oorg, oshp = CIO.overlay_region([ev_all[:, ::-1]] + [t[:, ::-1] for t in tested], CIO.PHERC1667_SCAN_SHAPE0)  # fixture scan
    head["overlay_region"] = dict(origin_zyx=[int(v) for v in oorg], shape_zyx=[int(v) for v in oshp], halo_um=380.0,
                                  rule="CONTRACT A10.2: bbox of scored pairs' PA/PB/midpoints and wrong-turn-tested vertices + halo, snapped to 128")
    # vertices.csv and wrong-turn / suspect points
    ov = np.zeros(oshp, np.uint8); wrong_pts = 0; wrong_patches = set(); wrong_xyz = {}; sus_n = {}
    with open(out / "vertices.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow("patch,row,col,z,y,x,wrap_index,theta,page,page_majority_n,n_ref,ref_ok,wrong_turn,suspect,max_risk".split(","))
        with zipfile.ZipFile(F / "patches.zip") as z:
            for p in allp:
                base = f"s4_{pc[p]['label']}_patches/patch_{p}/"
                X = tifffile.imread(io.BytesIO(z.read(base + "x.tif"))); Z = tifffile.imread(io.BytesIO(z.read(base + "z.tif")))
                rr, cc = np.where(np.isfinite(X) & (X > 0) & np.isfinite(Z) & (Z > 0))
                pg = page_of.get(p); sus = np.zeros(len(rr), bool)
                if evtree is not None:
                    sus = np.isfinite(evtree.query(pts[p], distance_upper_bound=3.0)[0])
                sus_n[p] = int(sus.sum())
                for q in range(len(rr)):
                    x, y, zz = pts[p][q]; ok_ = bool(okp[p][q]) and pg is not None
                    n = int(nref[p][q]) if ok_ else ""; wt = int(ok_ and n != maj[pg])
                    wrong_pts += wt
                    if wt:
                        wrong_patches.add(p); wrong_xyz.setdefault(p, []).append((x, y, zz))
                        iz, iy, ix = int(zz) - oorg[0], int(y) - oorg[1], int(x) - oorg[2]
                        if 0 <= iz < oshp[0] and 0 <= iy < oshp[1] and 0 <= ix < oshp[2]:
                            ov[iz, iy, ix] = 2
                    w.writerow([p, rr[q], cc[q], round(float(zz), 2), round(float(y), 2), round(float(x), 2), wrap.get(p, ("",))[0], round(float(th[p][q]), 5),
                                "" if pg is None else pg, "" if pg is None else maj[pg], n, int(ok_), wt, int(sus[q]), round(maxrisk.get(p, 0.0), 6)])
    # overlay: 1 = within 3 voxels of flagged evaluated points, 2 = wrong-turn vertices dilated by 1
    # (wrong-turn dilation by coordinates: same as binary_dilation(iterations=1) with the 6-neighbour cross, less memory)
    two = np.argwhere(ov == 2); ov[:] = 0
    for x, y, zz in ev:
        c = np.array([zz, y, x]) - oorg
        lo = np.maximum(np.floor(c - 3).astype(int), 0); hi = np.minimum(np.ceil(c + 3).astype(int) + 1, oshp)
        if np.any(lo >= hi):
            continue
        g = np.stack(np.meshgrid(*[np.arange(a, b) for a, b in zip(lo, hi)], indexing="ij"), -1)
        ov[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] |= (np.linalg.norm(g + 0.5 - c, axis=-1) <= 3).astype(np.uint8)
    for d in ((0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
        q = two + np.array(d); q = q[np.all((q >= 0) & (q < np.array(oshp)), axis=1)]
        ov[q[:, 0], q[:, 1], q[:, 2]] = 2
    CIO.write_overlay_fullframe(out / "overlay.zarr", ov, oorg, CIO.PHERC1667_SCAN_SHAPE0, name="contract overlay (example, region A)")
    # §4.1 clusters: flagged pairs by their evaluated points; wrong-turn patches by their wrong-turn vertices
    pair_pts = {}
    for i, r in enumerate(rows6):
        k = M.jkey(r["patch_a"], r["patch_b"])
        if k in flagged:
            m = P6["pair"] == i; pair_pts[k] = np.concatenate([P6["PA"][m], P6["PB"][m], (P6["PA"][m] + P6["PB"][m]) / 2]).astype(np.float64)   # §4.2: PA, PB and midpoint
    score = {M.jkey(r["patch_a"], r["patch_b"]): float(r["risk"]) for r in risk}
    thf = lambda xyz: ang(xyz, axis_xy); wk = {p: v[0] for p, v in wrap.items()}
    clusters = []
    for g in CIO.single_linkage(pair_pts):
        pat = sorted({p for k in g for p in k})
        clusters.append(CIO.cluster_record(len(clusters), "suspect_join", np.concatenate([pair_pts[k] for k in g]), pat, g, thf, wk,
                                           sum(sus_n.get(p, 0) for p in pat) * CIO.CELL_MM2 / 100, max(score[k] for k in g)))   # A7: suspect vertices x cell
    for g in CIO.single_linkage({p: np.asarray(v) for p, v in wrong_xyz.items()}):
        n = sum(len(wrong_xyz[p]) for p in g)
        clusters.append(CIO.cluster_record(len(clusters), "wrong_turn", np.concatenate([np.asarray(wrong_xyz[p]) for p in g]), g, [], thf, wk,
                                           n * CIO.CELL_MM2 / 100, None))   # A7: wrong-turn clusters have no pairs, so no switch score
    # cleaned tifxyz
    kept_cells = 0
    with zipfile.ZipFile(F / "patches.zip") as z:
        for p in allp:
            base = f"s4_{pc[p]['label']}_patches/patch_{p}/"; pg = page_of.get(p)
            if pg is None:
                continue
            arrs = {c: tifffile.imread(io.BytesIO(z.read(base + c + ".tif"))).copy() for c in "xyz"}
            valid = np.isfinite(arrs["x"]) & (arrs["x"] > 0) & np.isfinite(arrs["z"]) & (arrs["z"] > 0)
            rr, cc = np.where(valid); bad = okp[p] & (nref[p] != maj[pg])
            if bad.mean() > 0.5:
                continue
            kept_cells += int(len(rr) - bad.sum())
            d = out / "cleaned" / f"page_{pg:03d}" / f"patch_{p}"; d.mkdir(parents=True, exist_ok=True)
            for c in "xyz":
                arrs[c][rr[bad], cc[bad]] = -1; tifffile.imwrite(d / f"{c}.tif", arrs[c].astype(np.float32))
            meta = json.loads(z.read(base + "meta.json")); meta.update(contract="v1", removed_cells=int(bad.sum()),
                                                                        source_sha256={c: prov["patch_members_sha256"][base + c + ".tif"] for c in "xyz"})
            json.dump(meta, open(d / "meta.json", "w"), indent=1)
    json.dump(dict(**head, frame="scan voxels zyx, 7.91 um", wrap_index_source="CONTRACT.md §2", format="placeholder",
                   format_doc="phase/tools/SPIRAL_CONSTRAINTS.md", constraints=[]), open(out / "spiral_constraints.json", "w"), indent=1)
    # pipeline9 filter
    (out / "pipeline9").mkdir(exist_ok=True); rel = [r for r in csv.reader(open(F / "rel.csv")) if int(r[0]) in S and int(r[1]) in S]
    keep = [r for r in rel if M.jkey(*r[:2]) not in flagged]; rem = [r for r in rel if M.jkey(*r[:2]) in flagged]
    csv.writer(open(out / "pipeline9/rel_filtered.csv", "w", newline="")).writerows(keep)
    rk = {M.jkey(r["patch_a"], r["patch_b"]): float(r["risk"]) for r in risk}
    with open(out / "pipeline9/removed_joins.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patch_a", "patch_b", "risk", "sep_um", "contact", "reason"])
        for r in rem:
            k = M.jkey(*r[:2]); w.writerow([k[0], k[1], rk[k], sep.get(k, ""), int(sep.get(k, 1e9) < 50), "risk>=blind_threshold"])
    json.dump(dict(**head, rel_rows=len(rel), removed=len(rem), threshold=0.3293271860685008), open(out / "pipeline9/filter.json", "w"), indent=1)
    with open(out / "switch_risk.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patch_a", "patch_b", "risk", "flagged"])
        for r in risk:
            w.writerow([r["patch_a"], r["patch_b"], r["risk"], r["flagged"]])
    # report
    recs = M.page_records(pl, E, area, *M.cross_x6(M.load_x6_labels(F / "x6_pairs.csv")))
    mp = M.summarize_m2_point(M.m2_point_records(pl, E, th, tr, okp))
    rep = dict(**head, branch="<branch> (example writer)", inputs={"phase/data_small/fixture/provenance.json": hashlib.sha256((F / "provenance.json").read_bytes()).hexdigest()},
               counts=dict(patches=len(allp), patches_with_wrap_index=sum(p in wrap for p in allp), wrap_components=len({wrap[p][1] for p in allp if p in wrap}),
                           joins=len([k for k in {M.jkey(*r[:2]) for r in csv.reader(open(F / 'rel.csv'))} - flip1 if k[0] in S and k[1] in S]), pairs_scored=len(risk), pairs_flagged=len(flagged),
                           pairs_flagged_contact=sum(sep.get(k, 1e9) < 50 for k in flagged), pages=len(pl), wrong_turn_patches=len(wrong_patches), wrong_turn_points=int(wrong_pts)),
               areas_cm2=dict(patches_bbox=sum(area[p] for p in allp) / 100, pages=sum(area[p] for c in pl for p in c) / 100, flagged_suspect=sum(sus_n.values()) * CIO.CELL_MM2 / 100, wrong_turn=wrong_pts * CIO.CELL_MM2 / 100, cleaned_kept=kept_cells * CIO.CELL_MM2 / 100),
               metrics={"iii_rf_minus_flagged": dict(x6=M.summarize(recs), m2_point=mp)}, clusters=clusters)
    json.dump(rep, open(out / "report.json", "w"), indent=1, default=float)
    print(json.dumps(rep["counts"]))


if __name__ == "__main__":
    main(sys.argv[1])
