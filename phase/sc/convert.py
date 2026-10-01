"""Per-patch wrap index + risk  ->  villa Spiral relative winding constraints.

Input: a patches table (patch id, integer wrap index k in a cut gauge, optional risk in [0, 1],
optional abstain flag) and the edge table built by build_fixture.py (patch pair, seam term `cut`,
one anchor point on each patch, x,y,z in the dataset's voxel frame).

Output (in --out): relative_windings.json (VC3D point-collection JSON v1, the file the headless
fitter reads for the relative role), constraints.csv (one row per kept edge, contract-neutral) and
manifest.json. See CONTRACT_REQUEST.md for the villa semantics this relies on:
- wind_a differences are physical (seam-free) layer differences, so dphys = k_b - k_a - cut;
- every winding constraint is soft and villa has no per-point weight. DEFAULT is uniform: one copy
  per edge, w = 1 (SessE-2 (e): no risk has beaten chance at predicting a wrong constraint; see SessE.md).
  replicate mode (round(R * w) copies) and tiers mode (per-tier files + pcl_sampling_weights, service
  only) remain for a future risk that does.
Also writes the contract v1 §4.5 envelope spiral_constraints.json (records: phase/tools/SPIRAL_CONSTRAINTS.md).
Abstaining patches (abstain flag, or k missing) and every edge touching them are omitted.
"""
import argparse, hashlib, json
from pathlib import Path

import numpy as np
import pandas as pd

TIERS = ((0.9, 1.01, "hi"), (0.75, 0.9, "mid"), (0.0, 0.75, "lo"))


def edge_constraints(patches, edges, k_col, risk_col=None, abstain_col=None):
    """Return a DataFrame of kept edges: a, b, dphys, w, anchors. Pure function (tested)."""
    p = patches.set_index("patch")
    k = p[k_col]
    abstain = k.isna()
    if abstain_col is not None:
        abstain |= p[abstain_col].astype(bool)
    risk = p[risk_col] if risk_col is not None else pd.Series(0.0, index=p.index)
    a, b = edges["a"], edges["b"]
    keep = edges["has_anchor"] & ~abstain.reindex(a).values & ~abstain.reindex(b).values
    ka, kb = k.reindex(a).values, k.reindex(b).values
    dphys = kb - ka - edges["cut"]
    w = 1.0 - np.maximum(risk.reindex(a).values, risk.reindex(b).values)
    df = pd.DataFrame(dict(a=a, b=b, dphys=dphys, w=w,
                           ax=edges["pa_xyz"][:, 0], ay=edges["pa_xyz"][:, 1], az=edges["pa_xyz"][:, 2],
                           bx=edges["pb_xyz"][:, 0], by=edges["pb_xyz"][:, 1], bz=edges["pb_xyz"][:, 2]))[keep]
    df["dphys"] = df["dphys"].astype(int)
    return df.reset_index(drop=True)


def pcl_document(rows, copies, name_fmt):
    """VC3D point-collection JSON v1: one 2-point collection per (edge, copy)."""
    cols, cid = {}, 1
    for r, c in zip(rows.itertuples(index=False), copies):
        name = f"between_patches__{name_fmt.format(id=r.a)}__{name_fmt.format(id=r.b)}"
        for _ in range(int(c)):
            cols[str(cid)] = {"name": name, "color": [0.0, 0.0, 0.0], "metadata": {},
                              "points": {"1": {"p": [float(r.ax), float(r.ay), float(r.az)], "wind_a": 0.0, "creation_time": 0},
                                         "2": {"p": [float(r.bx), float(r.by), float(r.bz)], "wind_a": float(r.dphys), "creation_time": 0}}}
            cid += 1
    return {"vc_pointcollections_json_version": "1", "collections": cols}


def write(rows, out, mode="uniform", replicas=4, name_fmt="{id}", label="", extra=None, envelope=None):
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    if mode == "uniform":
        rows = rows.assign(w=1.0, copies=1)
        files["relative_windings.json"] = pcl_document(rows, np.ones(len(rows), int), name_fmt)
        sampling = None
    elif mode == "replicate":
        copies = np.rint(replicas * rows["w"].values).astype(int)
        rows = rows.assign(copies=copies)
        files["relative_windings.json"] = pcl_document(rows, copies, name_fmt)
        sampling = None
    elif mode == "tiers":
        rows = rows.assign(tier=[next(t for lo, hi, t in TIERS if lo <= w < hi) for w in rows["w"]], copies=1)
        sampling = {}
        for lo, hi, t in TIERS:
            sub = rows[rows.tier == t]
            files[f"relative_windings__{t}.json"] = pcl_document(sub, np.ones(len(sub), int), name_fmt)
            sampling[f"relative_windings__{t}"] = float(sub["w"].mean()) if len(sub) else 0.0
    else:
        raise ValueError(mode)
    digests = {}
    for fn, doc in files.items():
        raw = json.dumps(doc, separators=(",", ":")).encode()
        (out / fn).write_bytes(raw)
        digests[fn] = hashlib.sha256(raw).hexdigest()
    rows.to_csv(out / "constraints.csv", index=False)
    if envelope is not None:
        env = dict(envelope, format="sc.villa-relative-pairs/1", format_doc="phase/tools/SPIRAL_CONSTRAINTS.md",
                   frame="scan voxels zyx, 7.91 um", wrap_index_source="§2",
                   villa_files=digests, weighting=mode,
                   constraints=[dict(patch_a=int(r.a), patch_b=int(r.b), delta_winding=int(r.dphys), weight=float(r.w),
                                     copies=int(r.copies), point_a_zyx=[float(r.az), float(r.ay), float(r.ax)],
                                     point_b_zyx=[float(r.bz), float(r.by), float(r.bx)]) for r in rows.itertuples(index=False)])
        raw = json.dumps(env, separators=(",", ":")).encode()
        (out / "spiral_constraints.json").write_bytes(raw); digests["spiral_constraints.json"] = hashlib.sha256(raw).hexdigest()
    manifest = dict(schema="sc.villa-winding-constraints/1", label=label, mode=mode, replicas=replicas if mode == "replicate" else None,
                    pcl_sampling_weights=sampling, patch_name_format=name_fmt, n_edges=len(rows),
                    n_collections=int(rows["copies"].sum()), dphys_counts={str(k): int(v) for k, v in rows["dphys"].value_counts().sort_index().items()},
                    frame="x,y,z voxels of the dataset volume; fixture: PHerc1667 20231117161658 7.91 um level 0",
                    files=digests, **(extra or {}))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--patches", default=str(Path(__file__).parent / "fixture/patches.csv"))
    ap.add_argument("--edges", default=str(Path(__file__).parent / "fixture/edges.npz"))
    ap.add_argument("--index", choices=("q3c", "x7v9"), default="q3c",
                    help="q3c: contract v1 §2 k_q3c (fixture/k_q3c.csv); x7v9: SessE-1's k_ours")
    ap.add_argument("--k-col", default=None, help="override the index column (e.g. k_ref for the oracle arm)")
    ap.add_argument("--risk-col", default="risk", help="'none' gives w = 1 everywhere")
    ap.add_argument("--abstain-col", default="abstain", help="'none' abstains only where k is missing")
    ap.add_argument("--mode", choices=("uniform", "replicate", "tiers"), default="uniform")
    ap.add_argument("--git", default="", help="producer git head for the contract envelope")
    ap.add_argument("--replicas", type=int, default=4)
    ap.add_argument("--patch-name-format", default="{id}", help="must equal the verified_patches/ directory names")
    ap.add_argument("--label", default="ours")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    patches = pd.read_csv(a.patches)
    edges = dict(np.load(a.edges))
    inputs = {a.patches: hashlib.sha256(Path(a.patches).read_bytes()).hexdigest(), a.edges: hashlib.sha256(Path(a.edges).read_bytes()).hexdigest()}
    k_col = a.k_col or ("k_q3c" if a.index == "q3c" else "k_ours")
    if a.index == "q3c":
        kq = Path(a.patches).with_name("k_q3c.csv")
        patches = patches.merge(pd.read_csv(kq)[["patch", "k_q3c"]], on="patch")
        inputs[str(kq)] = hashlib.sha256(kq.read_bytes()).hexdigest()
    none = lambda s: None if s == "none" else s
    rows = edge_constraints(patches, edges, k_col, none(a.risk_col), none(a.abstain_col))
    z, y, x = edges["pa_xyz"][:, 2], edges["pa_xyz"][:, 1], edges["pa_xyz"][:, 0]
    region = dict(origin_zyx=[int(np.floor(np.nanmin(v))) for v in (z, y, x)],
                  shape_zyx=[int(np.ceil(np.nanmax(v)) - np.floor(np.nanmin(v)) + 1) for v in (z, y, x)])
    env = dict(contract="v1", git=a.git, region=region, inputs=inputs, label=a.label)
    m = write(rows, Path(a.out), a.mode, a.replicas, a.patch_name_format, a.label, envelope=env,
              extra=dict(inputs=inputs, k_col=k_col, risk_col=a.risk_col, abstain_col=a.abstain_col))
    print(json.dumps({k: v for k, v in m.items() if k != "inputs"}, indent=1))


if __name__ == "__main__":
    main()


# ---------------- contract Amendment 2: point-level role files (SessE-3) ----------------
def role_document(pts, same):
    """VC3D PCL JSON for point pairs (DataFrame with a, b, dphys, ax..bz). same=True: no wind_a (same-winding role)."""
    cols = {}
    for cid, r in enumerate(pts.itertuples(index=False), start=1):
        pa = {"p": [float(r.ax), float(r.ay), float(r.az)], "creation_time": 0}
        pb = {"p": [float(r.bx), float(r.by), float(r.bz)], "creation_time": 0}
        if not same:
            pa["wind_a"], pb["wind_a"] = 0.0, float(r.dphys)
        cols[str(cid)] = {"name": f"between_patches__{r.a}__{r.b}", "color": [0.0, 0.0, 0.0], "metadata": {},
                          "points": {"1": pa, "2": pb}}
    return {"vc_pointcollections_json_version": "1", "collections": cols}


def write_points(pts, out, envelope):
    """Amendment 2 layout: <out>/spiral/{same_windings,relative_windings}.json + <out>/spiral_constraints.json manifest."""
    (out / "spiral").mkdir(parents=True, exist_ok=True)
    rows = []
    for fn, sub, same in (("same_windings.json", pts[pts.dphys == 0], True), ("relative_windings.json", pts[pts.dphys != 0], False)):
        raw = json.dumps(role_document(sub, same), separators=(",", ":")).encode()
        (out / "spiral" / fn).write_bytes(raw)
        rows.append(dict(file=f"spiral/{fn}", sha256=hashlib.sha256(raw).hexdigest(), collections=len(sub),
                         patch_pairs=int(sub[["a", "b"]].drop_duplicates().shape[0])))
    env = dict(envelope, frame="scan voxels zyx, 7.91 um", wrap_index_source="§2", format="vc_pointcollections_json v1",
               format_doc="phase/tools/CONTRACT.md Amendment 2", weighting="uniform (one collection per point pair)",
               constraints=rows)
    (out / "spiral_constraints.json").write_text(json.dumps(env, indent=1) + "\n")
    return env
