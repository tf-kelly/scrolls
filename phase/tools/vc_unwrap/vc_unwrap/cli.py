"""vc-unwrap: one command from patches + scan + axis to per-wrap surfaces.

  vc-unwrap run --fixture --villa VILLA/spiral-fitting --steps 200 --out U          fixture region A, end to end (GPU)
  vc-unwrap run --origin Z Y X --shape Z Y X --patches P.zip --ct SCAN --rel rel.csv --axis-file axis.txt \\
                --villa VILLA/spiral-fitting --steps 30000 --out U                  any chunk-aligned region
  vc-unwrap run ... --until export                                                   everything a CPU can do (check + export)

Stages (each can be run alone on an existing OUT: `vc-unwrap check|export|fit|surfaces`):
  check     SessA's region check with the reference-free wrap solve (CONTRACT §2): OUT/check/ holds wrap_index.csv,
            unsatisfied.csv (the review list), pairs.csv, switch_risk.csv, report.json and overlay.zarr (the flags)
  export    villa Spiral dataset from OUR wrap index and label-free witness anchors: OUT/dataset/ (SessE's converter,
            snap, loader filter and name check, unmodified)
  fit       villa's fit_spiral.py at f4570bf, unchanged, arm (a) settings (NVIDIA GPU required): OUT/fit/
  surfaces  one tifxyz per winding from the fitted checkpoint: OUT/surfaces/winding_NNN/, windings.csv
OUT/UNWRAP_MANIFEST.json records inputs, versions, stage results and hashes. Exit codes: 0 ok, 2 invalid input or a
refused stage (the message says why), 3 internal error."""
import argparse, json, os, subprocess, sys, time, traceback
from pathlib import Path

from . import VILLA_COMMIT

STAGES = ("check", "export", "fit", "surfaces")


def repo_root(arg):
    if arg:
        return Path(arg).resolve()
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "phase/tools/CONTRACT.md").exists():
            return p
    raise SystemExit("cannot find the repository root; pass --repo")


def git(path, *a):
    r = subprocess.run(["git", "-C", str(path), *a], capture_output=True, text=True); return r.stdout.strip() if r.returncode == 0 else None


def load_manifest(out):
    f = out / "UNWRAP_MANIFEST.json"
    return json.load(open(f)) if f.exists() else dict(tool="vc-unwrap", stages={})


def save_manifest(out, m):
    (out / "UNWRAP_MANIFEST.json").write_text(json.dumps(m, indent=1, default=str) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vc-unwrap", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=("run",) + STAGES)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", help="repository root (default: found from the package location)")
    g = ap.add_argument_group("inputs (check)")
    g.add_argument("--fixture", action="store_true", help="fixture region A with its committed inputs and the contract axis")
    g.add_argument("--origin", type=int, nargs=3, metavar=("Z", "Y", "X")); g.add_argument("--shape", type=int, nargs=3, metavar=("Z", "Y", "X"))
    g.add_argument("--patches", nargs="+", help="zip(s)/dir(s) of tifxyz patch_N/ folders")
    g.add_argument("--patch-table"); g.add_argument("--ct", help="scan: OME-Zarr URL or local crop")
    g.add_argument("--scan-shape", type=int, nargs=3, metavar=("Z", "Y", "X"))
    g.add_argument("--rel", help="pipeline9 rel.csv (joins)"); g.add_argument("--axis-file", help="scroll axis, 'z, y, x' per line (required)")
    g.add_argument("--flip1", help="flip=1-only pair list for these patches (required outside --fixture; region mode would "
                                   "otherwise fall back to Scroll 4 slab 2's list, item-159)")
    g.add_argument("--spacing-um", help="wrap solve spacing (um) or 'estimate' (required outside --fixture; the fixture's is 134)")
    g.add_argument("--tile-core", type=int, nargs=3, metavar=("Z", "Y", "X")); g.add_argument("--workers", type=int)
    g.add_argument("--risk-model")
    f = ap.add_argument_group("fit")
    f.add_argument("--villa", help="villa's spiral-fitting directory at f4570bf (export's filters and the fit use it)")
    f.add_argument("--steps", type=int, default=30000)
    f.add_argument("--python", default=sys.executable, help="python with villa's dependencies (villa's `uv sync --frozen` env); used for export's filters, fit and surfaces")
    f.add_argument("--sync", help="shell command run during and after the fit, e.g. 'gsutil -m rsync -r OUT gs://BUCKET/PREFIX'")
    f.add_argument("--sync-every", type=int, default=300)
    f.add_argument("--capacity-windings", type=int, help="villa model_gap_expander_capacity_windings; default max(144, "
                   "windings + 14); set higher for an uncertain axis (item-164). Must be >= windings + 3")
    f.add_argument("--capacity-source", help="where --capacity-windings comes from (recorded)")
    f.add_argument("--surface-step", type=int, help="surface grid step in voxels (default: the checkpoint's)")
    s_ = ap.add_argument_group("scroll facts (set explicitly; each is recorded with its source)")
    s_.add_argument("--scroll-name", help="scroll name for spiral-scroll.json (required except with --fixture)")
    s_.add_argument("--voxel-um", type=float, help="scan voxel size in um (required except with --fixture)")
    s_.add_argument("--outward-sense", choices=("CW", "ACW"), help="villa spiral_outward_sense (default: CW derived from the solve's s = +1)")
    s_.add_argument("--num-windings", type=int, help="villa model_gap_expander_num_windings and shell_outer_winding_idx (required for fit)")
    s_.add_argument("--scroll-source", default="given on the command line", help="where --scroll-name/--voxel-um/--num-windings come from (recorded)")
    ap.add_argument("--until", choices=STAGES, help="with `run`: stop after this stage")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    try:
        return _run(a, out)
    except SystemExit as e:
        if e.code in (0, None):
            return 0
        print(f"vc-unwrap: {e.code}", file=sys.stderr); _record_error(out, str(e.code)); return 2
    except Exception as e:  # noqa: BLE001
        traceback.print_exc(); _record_error(out, f"{type(e).__name__}: {e}"); return 3


def _record_error(out, msg):
    m = load_manifest(out); m["status"] = "error"; m["error"] = msg; save_manifest(out, m)


def _run(a, out):
    repo = repo_root(a.repo); m = load_manifest(out)
    m.update(repo=str(repo), repo_commit=git(repo, "rev-parse", "HEAD"), villa_expected=VILLA_COMMIT, status="running")
    if a.villa:
        m["villa"] = dict(path=str(Path(a.villa).resolve()), commit=git(a.villa, "rev-parse", "HEAD"))
        if m["villa"]["commit"] not in (None, VILLA_COMMIT):
            raise SystemExit(f"villa is at {m['villa']['commit']}, not {VILLA_COMMIT} (git -C VILLA checkout {VILLA_COMMIT[:7]})")
    todo = STAGES[:STAGES.index(a.until) + 1] if (a.stage == "run" and a.until) else (STAGES if a.stage == "run" else (a.stage,))
    inp = m.get("inputs")
    if "check" in todo:
        from .check import fixture_args
        if a.fixture:
            inp = fixture_args(repo)
        else:
            need = [k for k in ("origin", "shape", "patches", "ct", "rel", "axis_file", "scan_shape", "flip1", "spacing_um")
                    if getattr(a, k) is None]  # item-159: no Scroll 4 defaults
            if need:
                raise SystemExit("check needs " + ", ".join("--" + k.replace("_", "-") for k in need) + " (or --fixture)")
            inp = dict(origin=a.origin, shape=a.shape, patches=[str(Path(p).resolve()) for p in a.patches], ct=a.ct, rel=str(Path(a.rel).resolve()),
                       axis_file=str(Path(a.axis_file).resolve()), patch_table=a.patch_table, scan_shape=a.scan_shape,
                       flip1=str(Path(a.flip1).resolve()))
        inp.update(spacing_um=a.spacing_um or ("134" if a.fixture else None), tile_core=a.tile_core, workers=a.workers, risk_model=a.risk_model)
        if a.fixture:
            # item-159: the fixture's own handedness objectives tie (65 vs 65), so its sense cannot come from the solve; it
            # comes from villa's catalogue rule for scan 20231117161658 (z top-to-bottom false, left-handed false -> CW; SessB instruction)
            sc = dict(name="PHerc1667", voxel_size_um=7.91, spiral_outward_sense=a.outward_sense or "CW", num_windings=a.num_windings or 130,
                      source=dict(name="fixture: PHerc1667 (Scroll 4) slab 2", voxel_size_um="fixture: 7.91 um scan",
                                  num_windings="fixture: villa f4570bf's default 130, kept explicitly (the fixture's winding numbers span far fewer)"))
        else:
            sc = dict(name=a.scroll_name, voxel_size_um=a.voxel_um, spiral_outward_sense=a.outward_sense, num_windings=a.num_windings,
                      source={k: a.scroll_source for k in ("name", "voxel_size_um", "num_windings")})
        if a.outward_sense:
            sc["source"]["spiral_outward_sense"] = a.scroll_source if not a.fixture else "given on the command line"
        elif a.fixture:
            sc["source"]["spiral_outward_sense"] = ("catalogue: PHerc1667 20231117161658, z_direction_is_top_to_bottom false, "
                                                    "left_handed_coordinates false -> CW by villa f4570bf's rule (SessB instruction); the "
                                                    "fixture's solve ties 65/65, so it is not derived from s")
        inp["scroll"] = sc
        m["inputs"] = inp
    if inp is None:
        raise SystemExit(f"{out} has no check stage yet (run `vc-unwrap check` first)")
    zr = [inp["origin"][0], inp["origin"][0] + inp["shape"][0]]
    for st in todo:
        t0 = time.time(); print(f"[vc-unwrap] {st} ...", flush=True)
        if st == "check":
            from .check import run_region, layout
            chk = run_region(inp, out); lay = layout(chk, inp["axis_file"], out / "run")
            rep = json.load(open(chk / "report.json")); wi = json.load(open(chk / "wrap_index.json"))
            res = dict(counts=rep.get("counts"), overlay_region=rep.get("overlay_region"), wrap_index={k: wi.get(k) for k in ("n", "n_components", "s_chosen", "n_unsatisfied", "spacing_um")},
                       layout=lay, overlay=str(chk / "overlay.zarr"))
        elif st == "export":
            from .export import run_export
            res = run_export(out, repo, inp["patches"], inp["axis_file"], zr, villa=a.villa, python=a.python, scroll=inp.get("scroll"))
            res = {k: v for k, v in res.items() if k not in ("files", "snap", "loader_filter")} | dict(manifest="EXPORT_MANIFEST.json")
        elif st == "fit":
            if not a.villa:
                raise SystemExit("fit needs --villa (villa's spiral-fitting directory at f4570bf)")
            from .fit import run_fit
            sc = inp.get("scroll") or {}
            res = run_fit(out, a.villa, zr, a.steps, sync_cmd=a.sync, sync_every=a.sync_every, python=a.python,
                          num_windings=sc.get("num_windings"), num_windings_source=(sc.get("source") or {}).get("num_windings"),
                          capacity_windings=a.capacity_windings, capacity_source=a.capacity_source)
        else:
            if not a.villa:
                raise SystemExit("surfaces needs --villa")
            ss = inp.get("scan_shape")
            if not ss:  # item-159: never fall back to Scroll 4's shape; it would mask a larger scan's surfaces as "outside"
                raise SystemExit("surfaces needs the run's scan shape; it is recorded by `vc-unwrap check --scan-shape Z Y X`")
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            r = subprocess.run([a.python, "-m", "vc_unwrap.surfaces", str(out), str(Path(a.villa).resolve()), str(a.surface_step or "-"), *map(str, ss)],
                               env=env, capture_output=True, text=True)
            (out / "surfaces").mkdir(exist_ok=True); (out / "surfaces/surfaces.log").write_text(r.stdout + r.stderr)
            if r.returncode:
                raise SystemExit(f"surfaces: exited {r.returncode} (see {out / 'surfaces/surfaces.log'})")
            res = json.load(open(out / "surfaces/SURFACES_RECORD.json"))
        m["stages"][st] = dict(result=res, wall_s=round(time.time() - t0, 1), done_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        save_manifest(out, m); print(json.dumps({st: res}, indent=1, default=str)[:1500], flush=True)
        if a.sync and st != "fit":
            subprocess.run(a.sync, shell=True)
    m["status"] = "ok"; save_manifest(out, m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
