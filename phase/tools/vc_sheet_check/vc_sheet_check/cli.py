"""vc-sheet-check: layer-jump checks for VC meshes, writing contract v1 §4 outputs.

  vc-sheet-check region  --origin Z Y X --shape Z Y X --patches ZIP|DIR ... --out DIR [...]
  vc-sheet-check segment MESH (tifxyz dir or .obj) --ct URL|ZARR --out DIR
  vc-sheet-check fixture --out DIR      (region A of phase/data_small/fixture with its committed inputs)
  vc-sheet-check solve   --slab2 | --edges EDGES.json  --spacing-um UM|estimate  --out DIR
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import sources as SRC


def _repo(arg):
    if arg:
        return Path(arg).resolve()
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "phase/tools/CONTRACT.md").exists():
            return p
    raise SystemExit("cannot find the repository (phase/tools/CONTRACT.md); pass --repo")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vc-sheet-check", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="repository root (default: found from the package location)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("region", help="patch set in a chunk-aligned region -> all §4 outputs")
    r.add_argument("--origin", type=int, nargs=3, required=True, metavar=("Z", "Y", "X"))
    r.add_argument("--shape", type=int, nargs=3, required=True, metavar=("Z", "Y", "X"))
    r.add_argument("--patches", nargs="+", required=True, help="zip(s)/dir(s) of tifxyz patch_N/ folders or pipeline9 .bin")
    r.add_argument("--patch-table", help="phase/x1/patches.csv-style table (bbox areas; default: computed from the grids)")
    r.add_argument("--ct", default=SRC.SCROLL4_URL, help="CT zarr: URL of the scan or a local OME-Zarr crop")
    r.add_argument("--scan-shape", type=int, nargs=3, default=[11174, 3340, 3440], metavar=("Z", "Y", "X"),
                   help="L0 scan shape for overlay_vc3d.zarr (default PHerc1667 20231117161658)")
    r.add_argument("--rel", required=True, help="pipeline9 rel.csv")
    r.add_argument("--flip1", help="flip=1-only pair list to exclude (default phase/x10/flip1_pairs.csv)")
    r.add_argument("--wrap-index", help="wrap index CSV to read (p1b_q3c_k.csv layout); omitted: solve it from this region's "
                   "own witness (contract §2; writes wrap_index.csv and wraps/)")
    r.add_argument("--edges", help="direct measurements d_i/d_ii for (iii-rf) (default phase/x10/x7_v7_edges.csv)")
    r.add_argument("--features", help="committed pair feature table (reproduction mode: flags come from it)")
    r.add_argument("--badpatchscores", help="pipeline9 badpatchscores_b.csv (stevens_dist_vox)")
    r.add_argument("--x6-pairs"); r.add_argument("--x6-points"); r.add_argument("--defects")
    r.add_argument("--reference", help="npz with xyz, u, t_ref (x4-upsampled reference) for wrong-turn points and M2")
    r.add_argument("--page-min-mm2", type=float, default=100.0)
    r.add_argument("--axis", choices=["x6", "table"], default="x6")
    r.add_argument("--no-field", action="store_true", help="skip the field (only with --features)")
    r.add_argument("--period-um", type=float, help="field period in um (default 118.6695, contract)")
    r.add_argument("--halo-um", type=float, help="halo in um (default 380 = 48 L0 voxels, CONTRACT A7.1)")
    r.add_argument("--keep-work", action="store_true")
    r.add_argument("--no-overlay", action="store_true", help="skip overlay.zarr (SessA-14); all other outputs unchanged")
    r.add_argument("--tile-core", type=int, nargs=3, metavar=("Z", "Y", "X"),
                   help="tile the field: core size in L0 voxels (e.g. 768 512 512); fields cover core + halo, one per tile")
    r.add_argument("--workers", type=int, default=3, help="tile worker processes (--tile-core)")
    r.add_argument("--field-cpu-cap-h", type=float, help="stop building tiles past this many CPU-hours")
    r.add_argument("--axis-file", help="scroll axis 'z, y, x' per line; overrides --axis for the field, theta and the solve")
    r.add_argument("--risk-model", help="switch-score model joblib (default phase/tools/risk_model/risk_model_v2_noz.joblib; "
                   "the fixture uses risk_model_v1.joblib)")
    r.add_argument("--compare-wrap-index", help="when solving: a wrap index to compare with (per-component constant removed)")
    r.add_argument("--spacing-um", default="estimate", help="solve spacing in um, or 'estimate' (SessC's CT band spacing over the region)")
    r.add_argument("--out", required=True)

    s = sub.add_parser("segment", help="one tifxyz/OBJ mesh -> dense per-pair crossing flags, clusters with a power statement")
    s.add_argument("mesh"); s.add_argument("--ct", required=True); s.add_argument("--out", required=True)
    s.add_argument("--crop", type=int, nargs=6, metavar=("Z", "Y", "X", "NZ", "NY", "NX"),
                   help="check only vertices inside this L0 box (for segments too large for a full-bbox field)")
    s.add_argument("--period-um", type=float, help="field period in um (default 118.6695, contract)")
    s.add_argument("--halo-um", type=float, help="halo around the mesh bbox in um (default 380 = 48 L0 voxels, CONTRACT A7.1)")
    s.add_argument("--axis-file", help="scroll axis, one 'z, y, x' per line (umbilicus); REQUIRED (CONTRACT A5.3)")
    s.add_argument("--pairs-per-cm2", type=float, help="sample pairs at this density instead of dense evaluation (the only knob)")
    s.add_argument("--scan-shape", type=int, nargs=3, metavar=("Z", "Y", "X"), help="L0 scan shape, only for a local CT crop")
    s.add_argument("--keep-work", action="store_true")

    f = sub.add_parser("fixture", help="run `region` on fixture region A with its committed inputs")
    f.add_argument("--out", required=True); f.add_argument("--ct", help="default: the fixture's local ct.zarr")
    f.add_argument("--features-mode", choices=["committed", "recomputed"], default="committed")
    f.add_argument("--keep-work", action="store_true")

    v = sub.add_parser("solve", help="wrap index (Q3c reference-free solve) with the spacing as a parameter")
    src = v.add_mutually_exclusive_group(required=True)
    src.add_argument("--slab2", action="store_true", help="Q3c's committed slab-2 inputs (x6b, X3 slab-2 pairs, x1 patches)")
    src.add_argument("--edges", help="solve_edges.json written by a solving region run")
    v.add_argument("--spacing-um", default="134", help="spacing in um, or 'estimate' (needs --ct; boxes from the edge points)")
    v.add_argument("--ct", default=SRC.SCROLL4_URL); v.add_argument("--scan-shape", type=int, nargs=3, default=[11174, 3340, 3440])
    v.add_argument("--compare", help="wrap index CSV to compare with (per-component constant removed)")
    v.add_argument("--features", help="recomputed_features.csv of the run the edges came from (testability columns of unsatisfied.csv)")
    v.add_argument("--terms", default="i,ii,iii", help="measurements in the LP: any of i (crossing count), ii (radial "
                   "separation / spacing), iii (Stevens / same-wrap); default all three (Q3c)")
    v.add_argument("--no-tiebreak", action="store_true", help="the committed HiGHS path without the SessA-15 tie-break (reproduction of results before SessA-15)")
    v.add_argument("--out", required=True)

    a = ap.parse_args(argv)
    return _guarded(a, lambda: _dispatch(a))


def _guarded(a, fn):
    """Exit codes (CONTRACT A4.2): 0 success, 2 invalid input, 3 internal error; on 2/3 write report.json with
    status "error" and the message when the output directory is known, and no overlay."""
    from .segment import InputError
    import traceback
    try:
        return fn()
    except (InputError, FileNotFoundError) as e:
        code, msg = 2, str(e)
    except SystemExit as e:
        if e.code in (0, None):
            return 0
        code, msg = 2, str(e.code)
    except Exception as e:          # noqa: BLE001
        code, msg = 3, f"{type(e).__name__}: {e}"; traceback.print_exc()
    out = getattr(a, "out", None)
    if out:
        import shutil
        Path(out).mkdir(parents=True, exist_ok=True); shutil.rmtree(Path(out) / "overlay.zarr", ignore_errors=True)
        json.dump(dict(contract="v1", status="error", error=msg), open(Path(out) / "report.json", "w"), indent=1)
    print(f"error ({code}): {msg}", file=sys.stderr)
    return code


def _dispatch(a):
    repo = _repo(a.repo)
    if a.cmd == "segment":
        from . import segment
        rep = segment.run(a, repo)
    elif a.cmd == "solve":
        from . import solve as SV
        rep = SV.cli(a, repo)
        print(json.dumps({k: v for k, v in rep.items() if k in ("n", "n_components", "s_chosen", "objectives", "objective", "spacing_um", "compare")}, indent=1))
        return 0
    else:
        if a.cmd == "fixture":
            F = repo / "phase/data_small/fixture"
            reg = json.load(open(F / "provenance.json"))["regions"]["A_rich"]
            a = argparse.Namespace(
                origin=[reg["z"][0], reg["y"][0], reg["x"][0]], shape=[reg[k][1] - reg[k][0] for k in "zyx"],
                patches=[str(F / "patches.zip")], patch_table=str(F / "patches.csv"), ct=a.ct or str(F / "ct.zarr"),
                scan_shape=[11174, 3340, 3440], rel=str(F / "rel.csv"), flip1=None, edges=None,
                features=str(F / "pair_features.csv") if a.features_mode == "committed" else None,
                badpatchscores=None, x6_pairs=str(F / "x6_pairs.csv"), x6_points=str(F / "x6_points.npz"),
                defects=str(F / "golden/defects.csv"), reference=str(F / "reference_subset.npz"),
                page_min_mm2=json.load(open(F / "golden/pages_metrics.json"))["iii_rf"]["page_min_mm2"],
                axis="x6", no_field=False, keep_work=a.keep_work, out=a.out, period_um=None, halo_um=None,
                wrap_index=str(repo / "phase/p1page/p1b_q3c_k.csv"),        # the fixture golden is Q3c's committed index
                risk_model=str(repo / "phase/tools/risk_model/risk_model_v1.joblib"))   # ... and risk model v1's flags
        a.solve = not a.wrap_index                                           # CONTRACT §2: no index given -> solve
        # slab-2 defaults apply only with a committed (slab-2) index; a solving run is on an arbitrary region
        a.flip1 = a.flip1 or (None if a.solve else str(repo / "phase/x10/flip1_pairs.csv"))
        a.edges = a.edges or (None if a.solve else str(repo / "phase/x10/x7_v7_edges.csv"))
        if a.no_field and not a.features:
            raise SystemExit("--no-field needs --features")
        from . import region
        rep = region.run(a, repo)
    print(json.dumps(dict(counts=rep["counts"], resources=rep.get("resources")), indent=1))
    return 0


def main_a42(argv=None):
    """CONTRACT A4.2 command line, segment and region forms:
    vc_sheet_check --segment <tifxyz dir | .obj> --volume <ome-zarr root> --out <dir> [--halo-um 380]
                   [--threshold T] --axis-file <z,y,x csv>   (the axis file is required by A5.3)
    vc_sheet_check --region Z Y X NZ NY NX --patches <zip|dir> ... --rel <rel.csv> --volume <ome-zarr root> --out <dir>
                   [--wrap-index <csv>]   (omitted: the §2 solve runs on the region's own witness)
                   [--axis-file <z,y,x csv>] [--spacing-um N|estimate] [--tile-core Z Y X] [--flip1 <csv>]"""
    ap = argparse.ArgumentParser(prog="vc_sheet_check", description=main_a42.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--segment"); mode.add_argument("--region", type=int, nargs=6, metavar=("Z", "Y", "X", "NZ", "NY", "NX"))
    ap.add_argument("--volume", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--halo-um", type=float, default=None); ap.add_argument("--threshold", type=float, default=0.3293271860685008,
                                                                             help="switch-score threshold (region mode; recorded, unused in segment mode)")
    ap.add_argument("--axis-file"); ap.add_argument("--crop", type=int, nargs=6); ap.add_argument("--pairs-per-cm2", type=float)
    ap.add_argument("--scan-shape", type=int, nargs=3); ap.add_argument("--repo"); ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--patches", nargs="+"); ap.add_argument("--rel"); ap.add_argument("--flip1"); ap.add_argument("--wrap-index")
    ap.add_argument("--patch-table"); ap.add_argument("--spacing-um", default="estimate"); ap.add_argument("--tile-core", type=int, nargs=3)
    ap.add_argument("--workers", type=int, default=3); ap.add_argument("--page-min-mm2", type=float, default=100.0)
    ap.add_argument("--field-cpu-cap-h", type=float); ap.add_argument("--risk-model")
    ap.add_argument("--no-overlay", action="store_true", help="region mode: skip overlay.zarr (SessA-14); all other outputs unchanged")
    a = ap.parse_args(argv)
    if a.segment:
        ns = argparse.Namespace(cmd="segment", repo=a.repo, mesh=a.segment, ct=a.volume, out=a.out, crop=a.crop, period_um=None,
                                halo_um=a.halo_um, axis_file=a.axis_file, pairs_per_cm2=a.pairs_per_cm2, scan_shape=a.scan_shape,
                                keep_work=a.keep_work)
    else:
        if not a.patches or not a.rel:
            ns = argparse.Namespace(out=a.out)
            return _guarded(ns, lambda: (_ for _ in ()).throw(SystemExit("--region needs --patches and --rel")))
        ns = argparse.Namespace(cmd="region", repo=a.repo, origin=a.region[:3], shape=a.region[3:], patches=a.patches,
                                patch_table=a.patch_table, ct=a.volume, scan_shape=a.scan_shape or [11174, 3340, 3440], rel=a.rel,
                                flip1=a.flip1, wrap_index=a.wrap_index, edges=None, features=None, badpatchscores=None,
                                x6_pairs=None, x6_points=None, defects=None, reference=None, page_min_mm2=a.page_min_mm2,
                                axis="x6", no_field=False, period_um=None, halo_um=a.halo_um, keep_work=a.keep_work, out=a.out,
                                tile_core=a.tile_core, workers=a.workers, field_cpu_cap_h=a.field_cpu_cap_h, axis_file=a.axis_file,
                                spacing_um=a.spacing_um, compare_wrap_index=None, risk_model=a.risk_model,
                                no_overlay=a.no_overlay)
    return _guarded(ns, lambda: _dispatch(ns))


if __name__ == "__main__":
    sys.exit(main())
