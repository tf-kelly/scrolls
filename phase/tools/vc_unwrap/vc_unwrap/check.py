"""Stage 1, check: SessA's `vc-sheet-check region` run unchanged through its own main(), without --wrap-index, so it
solves the wrap index from the region's own witness (CONTRACT §2, A13.2). One capture hook (SessF's run_region.py,
<branch>): features.witness_features is wrapped so the witness arrays W and the pairs() arrays P, which region
mode keeps only in memory, are saved to OUT/check/_capture/. The hook returns exactly what the original returns.
Then the label-free run layout (SessF's run_layout.py): per-pair verdicts, and up to 10 evaluated point pairs per
non-coincident pair from SessA's own solve.edges_from_witness(return_points=True). No label, reference or X6 file is read."""
import csv, json, sys
from pathlib import Path

import numpy as np

FIXTURE_AXIS = "phase/tools/vc_sheet_check/validation/results/v1-12/run/axis_contract_allpatches_zyx.txt"


def fixture_args(repo):
    F = repo / "phase/data_small/fixture"; r = json.load(open(F / "provenance.json"))["regions"]["A_rich"]
    return dict(origin=[r["z"][0], r["y"][0], r["x"][0]], shape=[r[k][1] - r[k][0] for k in "zyx"], patches=[str(F / "patches.zip")],
                patch_table=str(F / "patches.csv"), ct=str(F / "ct.zarr"), rel=str(F / "rel.csv"), axis_file=str(repo / FIXTURE_AXIS),
                scan_shape=[11174, 3340, 3440])  # the fixture's scan, PHerc1667 20231117161658 (provenance.json "ct"); item-159


def run_region(a, out):
    """a: dict with origin, shape, patches, ct, rel, axis_file, spacing_um and optional patch_table, scan_shape, tile_core,
    workers, risk_model. Writes every SessA region output to OUT/check."""
    from vc_sheet_check import cli, features as FE
    chk = out / "check"; cap = chk / "_capture"; orig = FE.witness_features

    def hook(P, meta, rows, *x, **k):
        feats, W = orig(P, meta, rows, *x, **k)
        cap.mkdir(parents=True, exist_ok=True)
        np.savez(cap / "witness.npz", **W); np.savez(cap / "pairs_pts.npz", **P); np.save(cap / "meta_ids.npy", np.asarray(meta, np.int64))
        return feats, W

    argv = ["region", "--origin", *map(str, a["origin"]), "--shape", *map(str, a["shape"]), "--patches", *a["patches"],
            "--ct", a["ct"], "--rel", a["rel"], "--axis-file", a["axis_file"], "--spacing-um", str(a["spacing_um"]), "--out", str(chk)]
    for k, flag in (("patch_table", "--patch-table"), ("risk_model", "--risk-model"), ("workers", "--workers"), ("flip1", "--flip1")):
        if a.get(k) is not None:
            argv += [flag, str(a[k])]
    for k, flag in (("scan_shape", "--scan-shape"), ("tile_core", "--tile-core")):
        if a.get(k) is not None:
            argv += [flag, *map(str, a[k])]
    FE.witness_features = hook
    try:
        rc = cli.main(argv)
    finally:
        FE.witness_features = orig
    if rc != 0:
        raise SystemExit(f"check: vc-sheet-check region exited {rc} (see {chk}/report.json)")
    return chk


def layout(chk, axis_file, run):
    """Label-free layout from the region run: pairs.csv, points_labelfree.npz; checks the edges re-derived here equal the
    region run's own solve_edges.json."""
    from vc_sheet_check._vendor import switchwitness_core as SW
    from vc_sheet_check import solve as SV
    run.mkdir(parents=True, exist_ok=True)
    P = dict(np.load(chk / "_capture/pairs_pts.npz")); W = dict(np.load(chk / "_capture/witness.npz")); mids = np.load(chk / "_capture/meta_ids.npy")
    V, MED, AG, NT = SW.verdicts(W, len(mids))
    with open(run / "pairs.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["pair", "patch_a", "patch_b", "n_testable", "median_count", "agreement", "verdict"])
        for q, (a, b) in enumerate(mids):
            w.writerow([q, a, b, NT[q], "" if np.isnan(MED[q]) else int(MED[q]), "" if np.isnan(AG[q]) else round(AG[q], 3), V[q]])
    ax = np.loadtxt(axis_file, delimiter=","); axis = lambda z: (np.interp(z, ax[:, 0], ax[:, 2]), np.interp(z, ax[:, 0], ax[:, 1]))
    Pid = dict(P); Pid["meta"] = mids
    E, _, SA, SB, SI = SV.edges_from_witness(Pid, mids.tolist(), W, MED, V, axis, NT=NT, AG=AG, return_points=True)
    np.savez(run / "points_labelfree.npz", PA=SA.astype(np.float32), PB=SB.astype(np.float32), edge=SI.astype(np.int32),
             edge_patches=np.array([[e["a"], e["b"]] for e in E], np.int64))
    RE = json.load(open(chk / "solve_edges.json"))["edges"]
    same = sorted((int(e["a"]), int(e["b"])) for e in RE) == sorted((int(e["a"]), int(e["b"])) for e in E)
    if not same:
        raise SystemExit("check: edges re-derived from the witness differ from the region run's solve_edges.json")
    return dict(pairs=len(mids), verdicts={v: int((np.asarray(V) == v).sum()) for v in sorted(set(V))}, edges=len(E), point_pairs=int(len(SA)))
