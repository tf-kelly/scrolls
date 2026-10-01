# vc-unwrap

One command from a patch set, a scan and a scroll axis to per-wrap surfaces:

```
patches + scan + axis
  -> check     region check and reference-free wrap solve (vc_sheet_check; CONTRACT §2)
  -> export    Spiral constraints from OUR wrap index and label-free witness anchors (converter, snap, filters)
  -> fit       villa's Spiral fitter at f4570bf, unchanged (NVIDIA GPU required)
  -> surfaces  one tifxyz per winding from the fitted spiral, plus the flag overlay from the check
```

No reference, label or answer key is read at any stage.
- The constraint anchors are the check's own witness point pairs, not the reference's evaluated pairs (that
  dependency was a release blocker in an earlier audit).
- The wrap numbers are the solve's.
- Built on `vc_sheet_check` (region check and solve), `phase/sc` (converter, snap, loader filter, name check), the
  dataset layout and capture hook of the earlier fit runs, and the slab-2 fit settings.

## Five commands

```bash
pip install -r phase/tools/requirements.txt -e phase/tools/vc_sheet_check -e phase/tools/vc_unwrap     # 1. contract env (Python 3.11)
python3 phase/data_small/fixture/fetch_fixture.py                                                      #    fixture patches and CT, sha256-checked (needed before 3)
git clone --filter=blob:none https://github.com/ScrollPrize/villa && git -C villa checkout f4570bf \
  && (cd villa/spiral-fitting && uv sync --frozen)                                                     # 2. villa in its own env (Python >= 3.14)
vc-unwrap run --fixture --until export --villa villa/spiral-fitting \
  --python villa/spiral-fitting/.venv/bin/python --out U                                               # 3. check + export (CPU, about 3 min)
vc-unwrap fit --villa villa/spiral-fitting --python villa/spiral-fitting/.venv/bin/python --steps 200 --out U \
  && vc-unwrap surfaces --villa villa/spiral-fitting --python villa/spiral-fitting/.venv/bin/python --out U   # 4. fit (GPU) + per-wrap tifxyz
cat U/UNWRAP_MANIFEST.json; ls U/surfaces U/check/overlay.zarr                                         # 5. what was produced, with hashes
```

- Any other region: replace `--fixture` with `--origin Z Y X --shape Z Y X --patches P.zip --ct SCAN --rel rel.csv
  --axis-file axis.txt` (chunk-aligned L0 box; the axis is required, CONTRACT A5.3).
  Outside `--fixture`, `check` also **requires `--scan-shape Z Y X`, `--flip1 FLIP1.csv` and `--spacing-um`**
  (item-159): without them, region mode and `surfaces` fell back to Scroll 4's scan shape, Scroll 4 slab 2's flip-1
  list and a 134 µm spacing.
- **Scroll facts are explicit** for any region but the fixture: `--scroll-name`, `--voxel-um` and `--num-windings`, plus
  `--scroll-source` saying where they come from. `--outward-sense CW|ACW` is optional; without it, CW is derived from
  the solve's s = +1 only when the two handedness objectives differ; a tie, or s = −1, is refused (CONTRACT A18.3). All four values and their sources are recorded:
  `spiral-scroll.json` and `EXPORT_MANIFEST.json` (`scroll_spec`), `fit/config_overrides.json` and `FIT_RECORD.json`.
  - `--num-windings` sets villa's `model_gap_expander_num_windings` and `shell_outer_winding_idx`. At f4570bf both
    default to 130, Scroll 1's count, and the fit stage refuses to run without an explicit value.
  - It also sets `model_gap_expander_capacity_windings` to max(144, windings + 14). villa f4570bf refuses a
    capacity below `shell_outer_winding_idx` + 3 (`spiral_helpers.py:1160`), and its defaults keep 14 of headroom
    (item-163).
  - `--capacity-windings N --capacity-source "..."` overrides that (for an uncertain axis); below windings + 3 is refused.
  - **Exceed gate (item-164):** during the fit, `fit.log` is scanned every 10 s for villa's `WARNING: … exceeding
    gap_expander_capacity_windings` or `… exceeding flow_bounds_radius`; on a match the fit is stopped and fails, and the
    lines are kept in `FIT_RECORD.json` (villa itself only warns).
  - The fixture records PHerc1667, 7.91 µm and 130 explicitly, each with its source.
- For large regions add `--tile-core 768 512 512 --workers 4`.
- A full run in one command is `vc-unwrap run ... --steps 30000`.
- On a cloud machine add `--sync 'gsutil -m rsync -r U gs://BUCKET/PREFIX'`. Outputs are then pushed during the fit
  and after every stage, not only at exit (project owner, 2026-09-28: a job that uploads only at exit fails the merge
  screen).

## Requirements

- **Contract environment** (`phase/tools/requirements.txt`, Python 3.11, zarr 2.18.7): `check` and the in-process
  part of `export`.
  - `vc_sheet_check` must be the version in this tree (it has the solve subcommand and
    `solve.edges_from_witness(..., return_points=True)`).
- **villa's environment** (`--python`; villa's `uv.lock`, Python ≥ 3.14, torch with CUDA): `export`'s loader filter
  and name check (they import villa's own loader), `fit`, and `surfaces`.
  - villa must be at f4570bf; the tool refuses any other commit.
- **GPU:** `fit` needs an NVIDIA GPU. villa's fit selects CUDA unconditionally and uses Triton kernels.
  - A 30,000-step fit of slab 2 (768 × 3,456 × 3,456 L0 voxels) in 4,012 s on one L4, 2.84 GB of GPU memory.
  - The fixture region is 384³.
  - `check`, `export` and `surfaces` run on CPU.

## Outputs (`OUT/`)

| path | stage | what |
|---|---|---|
| `check/` | check | every region-check output: `wrap_index.csv` (k_q3c, component, thN), `wrap_index.json` (s, objective), `unsatisfied.csv` (the solve's review list), `pairs.csv`, `switch_risk.csv`, `report.json` (with `overlay_region`), **`overlay.zarr`** (the flag overlay, full frame, VC3D-readable, CONTRACT A4/A10) |
| `run/` | check | label-free layout: `pairs.csv` with verdicts, `points_labelfree.npz` (≤ 10 evaluated point pairs per non-coincident pair) |
| `dataset/` | export | villa dataset root: `verified_patches/<id>/`, `same_windings.json`, `relative_windings.json`, `umbilicus.json`, `spiral-scroll.json` |
| `EXPORT_MANIFEST.json`, `name_check.json` | export | constraint counts, snap and filter statistics, villa's name check, file hashes |
| `fit/` | fit | `run/checkpoint_fitted.ckpt`, `metrics.jsonl`, `fit.log`, `config_overrides.json`, `FIT_RECORD.json` |
| `surfaces/winding_NNN/` | surfaces | tifxyz (`x.tif`, `y.tif`, `z.tif`, `meta.json`) per winding of the fit; −1 outside the fit's z range or the scan |
| `surfaces/windings.csv` | surfaces | per winding: valid vertices, patch vertices within 4 voxels, and the modal wrap number of our index there (a diagnostic; the fit's winding indices are its own) |
| `UNWRAP_MANIFEST.json` | all | inputs, repository and villa commits, per-stage results and wall times, status |

Exit codes: 0 ok; 2 invalid input or a refused stage, with the message saying why; 3 internal error.

A stage refuses in these cases:
- the solve chose s = −1 (villa's CW sense is derived from s = +1);
- villa's own loader links a constraint to the wrong patch;
- no CUDA device is available for `fit`;
- villa is not at f4570bf.

## What the stages do not claim

- **The wrap index is the region's own solve.** On the fixture it has 6 components and is not the slab-wide committed
  index (the golden files use that one). So `test_fixture.py --outputs U/check` passes its format checks and fails
  its golden-equality checks by construction.
- **The switch flags** use the shipped v2_noz model. Its recall is a within-slab figure and is lower on held-out slabs.
- **The surfaces are the fitted spiral**, not a flattened page. Outer windings beyond the data are extrapolation;
  `windings.csv` shows which windings patches support.
- **A physical fit steered by our constraints** reached the reference's turn number on 0.568 of the 1,407 joins where
  it changes, against 0.361 unconstrained (slab 2). Later fits, including a held-out slab, are in `docs/CLAIMS.md` B1–B2.

## Tests

- On the fixture, CPU: `check` in 82 s (5.3 GB peak), then `export`, gave:
  - 229 patches, 6 components, s = +1;
  - 5,143 constraint point pairs, of which 5,077 were kept after villa's loader filter (2 patches not loaded in the
    z range);
  - villa's name check passed.
- `surfaces` was tested on CPU on a fitted slab-2 checkpoint: 121 windings in 23 s, nested and inside the
  scan after masking.
- The 200-step GPU fit on the fixture (command 4) has not been run.
