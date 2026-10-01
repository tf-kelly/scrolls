# Winding index and join checks for automated scroll unwrapping

This tree was built by script from a private repository (see *Release*).

## Abstract

On W. Stevens' released Scroll 4 patch set (56,968 patches, 56,934 of them numbered), a reference-free winding index
gives every patch a turn number from CT measurements alone (docs/CLAIMS.md A, B16). Used as winding constraints for
villa's Spiral fitter, it makes the fit follow the reference's turn changes on joins whose anchors are at least 50 µm
apart 0.963 of the time on one slab and 0.848 on a held-out slab, against 0.616 and 0.595 without constraints (B1, B2).
A join checker finds turn-changing joins at recall 0.872 at precision 0.85 within that slab, and 0.64 and 0.44 on two
held-out slabs (B4, B5). Many pre-registered predictions missed; each is listed with its threshold and observed value in
docs/CLAIMS.md section D. The reference is machine output, not ground truth.

## What it does

From a set of surface patches, a CT scan and a scroll axis, the tools:
1. solve a **reference-free wrap index**: an integer turn number for every patch, from CT measurements alone
   (`phase/tools/vc_sheet_check`; CLAIMS A, B6);
2. **check joins** between touching patches and flag where a join changes turn (CLAIMS B4, B5);
3. pass the turn numbers to villa's Spiral fitter as **winding constraints** and write one surface per turn
   (`phase/tools/vc_unwrap`; CLAIMS B1, B2, B7).

## Data (all with URLs)

- Scroll 4 patches: W. Stevens, report12, https://dl.ash2txt.org/community-uploads/will/s4_good_patches.zip (47,797)
  and https://dl.ash2txt.org/community-uploads/will/s4_bad_patches.zip (9,171),
  dl.ash2txt.org/community-uploads/will/. Our index assembles the full set and flags rather than removes.
- CT: PHerc 1667 (Scroll 4), volume 20231117161658 (7.91 µm):
  https://dl.ash2txt.org/full-scrolls/Scroll4/PHerc1667.volpkg/volumes_zarr/20231117161658.zarr
- Reference surface (scoring only, never an input): the PHerc 1667 complete unwrapping (arXiv 2606.29085), CC BY-NC 4.0,
  `s3://vesuvius-challenge-open-data/PHerc1667/segments/20260612121456-w011_20260108140509268_merged_v4_flatboi_straightened_v4/`.

## Pipeline



```
patches (tifxyz) + scan (OME-Zarr) + axis (txt)
  -> vc-sheet-check  region check + wrap solve   -> wrap_index.csv, unsatisfied.csv, overlay.zarr
  -> vc-unwrap export                            -> Spiral constraint JSONs (villa's format)
  -> villa Spiral fitter (unchanged, f4570bf)    -> fitted model
  -> vc-unwrap surfaces                          -> one tifxyz per winding + flag overlay
```

## Formats

| file | produced by | consumed by | format |
|---|---|---|---|
| patches | pipeline9 / grower | check | tifxyz directories (villa naming) |
| `wrap_index.csv` | check | export, pages | patch id, component, wrap number |
| `unsatisfied.csv` | check | review | solve terms left unsatisfied |
| `overlay.zarr` | check | VC3D plugin | contract overlay (`phase/tools/CONTRACT.md`) |
| constraint JSONs | export | villa fitter | villa `relative_windings.json` / same-winding collections |
| surfaces | surfaces | VC3D, renderers | tifxyz per winding |

## Quickstart (fixture, CPU)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r phase/tools/requirements.txt -e phase/tools/vc_sheet_check -e phase/tools/vc_unwrap
python3 phase/data_small/fixture/fetch_fixture.py   # fetch W. Stevens' patch members + region-A CT, sha256-checked (about 3 min)
python3 phase/tools/test_metrics.py && python3 phase/tools/test_fixture.py      # ~1.5 min on 4 CPUs; G7 runs the solver;
                                                     # test_metrics runs its synthetic checks and skips the ledger part (private data)
vc-unwrap run --fixture --until export --out U                                    # ~2 min (101 s on 4 CPUs)
```

The fit needs an NVIDIA GPU and villa in its own environment; see `phase/tools/vc_unwrap/README.md`.
The quickstart's `U/.../relative_windings.json` is the file **before** villa's loader filter and name check, which need
`--villa`. The whole-scroll fits read the loader-filtered `relative_windings.json`, sha256
`6e7e7d15378767c084ed1a66a39e1ec6cb6390ff7b953d09d215f21115601214` (in the community index package).
The quickstart above was run cold from a fresh clone on 30 Sep 2026 (4 CPUs, no GPU): every line exits 0.

## Running the fitter: settings that bite

Set these explicitly for any scroll; villa's defaults are tuned for Scroll 1.
- `num_windings` (default **130**) silently caps the fitted range, with no warning.
- `model_gap_expander_capacity_windings` (default **144**) must be at least the outermost shell index + 3, or model
  construction fails (CLAIMS E4). `vc-unwrap` sets max(144, windings + 14).
- `model_initial_dr_per_winding` (default **16** vox) is about half Scroll 4's pitch. With the dense-spacing inputs off
  (patch-only mode), the Scroll 4 fit produced about twice the turns (CLAIMS F14, F17); with the initial spacing at the
  published pitch, the unconstrained redo produced 44 windings against 95 (F15).

## Using the outputs

- **Index → fitter files.** `vc-unwrap run … --until export --villa villa/spiral-fitting --out U` runs the check and
  solve, then writes villa's Spiral constraint JSONs under `U/`. Next, `vc-unwrap fit` and `vc-unwrap surfaces`. The
  exact commands, and the scroll facts required outside the fixture, are in `phase/tools/vc_unwrap/README.md`
  ("Five commands").
- **Checker.**
  - CLI: `vc-sheet-check region --origin Z Y X --shape Z Y X --patches P.zip --rel rel.csv --ct SCAN` (join checks
    over a patch set) or `vc-sheet-check segment …` (one mesh). `vc-sheet-check fixture` runs `region` on the fixture.
    Run `vc-sheet-check <cmd> -h` for all arguments.
  - VC3D plugin: **Tools → Sheet check (joins)** runs join mode from the plugin's own menu on a small join spec
    (region, patches, `rel.csv`); see `phase/tools/vc3d_plugin/JOIN.md`. The headless menu test is
    `run_join_test.sh`. Single-patch (segment) mode from the menu does not yet complete. Build and other tests:
    `phase/tools/vc3d_plugin/README.md` ("Reproduce").
- **Flags list keyed by Stevens' ids.** `python3 community/build_s4_index.py OUT` writes:
  - `OUT/winding.csv`, with columns `patch_id, component, winding, theta_rad`;
  - `OUT/contradictions.json`, listing each join whose solved windings violate a constraint, with its required and
    solved differences.

  `patch_id` is the number `N` in Stevens' zip folder `s4_<good|bad>_patches/patch_N/` (report12 upload). Windings
  are comparable only within one `component`.

## Results

- **Fit steering** (B1, B2): joins with anchors ≥ 50 µm, fit follows the reference 0.963 (ours) / 0.616 (none) / 0.958 (oracle)
  on slab 2 (672 joins); 0.848 / 0.595 / 0.948 on held-out HO-A (402 joins).
- **Checker** (B4, B5): recall 0.872 at precision 0.85 within slab 2; leave-one-slab-out 0.86, 0.64, 0.44.
- **Whole-scroll fits** (B7): relative-winding pairs at ≥ 50 µm obeyed 0.934 with our constraints against 0.537 without
  (114,095 pairs).
- **Quilt coverage** (B15): 648.3 cm² of projected trace coverage (an upper bound on verified surface); 823.44 cm² as a
  3-D union (4-vox grid); 20/20 random trace cells judged single-sheet by one blind reader.
- **Published pages** (B13, B14): sheet crossings located on two of W. Stevens' pages, confirmed blind; page 5 unresolved.
- **Community index** (B18): `winding.csv`, `contradictions.json` and the constraint files; built by
  `community/build_s4_index.py` (see Reproduce).
- **Misses:** docs/CLAIMS.md section D.

## Limits

- Below 25 µm anchor separation nothing, the oracle included, follows the reference (F1).
- The fitter ran in patch-only mode (no dense-spacing inputs published for this volume); with its default initial spacing
  it doubled the turn count (F14, F15, F17).
- In the outermost windings the index and the published numbering diverge (F14); at contacts, at most 7/20 of the index's
  turn changes are unsupported by a blind reader (F19).
- The shipped tests did not exercise the solver until a cold run caught it; test G7 now does.

## Future work

- Dense-spacing inputs for the fitter on this volume.
- Joining index components across separately indexed slabs.

## Reproduce

**Scroll 4 community index:** `mkdir -p OUT && python3 community/build_s4_index.py OUT` writes `OUT/winding.csv` and
`OUT/contradictions.json` from `community/wrap_index.csv` and `community/unsatisfied.csv` (the script
asserts both input hashes). **Claims register:** `docs/CLAIMS.md` is a release copy of the private register;
sections and rows outside this release's scope are removed and entry IDs are unchanged.

**Dependencies:** Python ≥ 3.10 (tested 3.11) with `phase/tools/requirements.txt` (numpy, scipy, scikit-learn,
scikit-image, zarr 2, numcodecs, tifffile, imagecodecs, matplotlib, pandas, pillow, ortools 9.15.6755 for the solve); villa at commit f4570bf
(`spiral-fitting`, its own Python ≥ 3.14 environment via `uv sync --frozen`); an NVIDIA GPU for the fit; torch for
the `vc_unwrap` CPU fixture test (it fails without it); Apptainer and the cluster scripts in `phase/arc/` for the
whole-scroll fits.

**Inputs and what is private:**
- The fixture's own files and golden outputs are in `phase/data_small/fixture`. Its third-party parts are **fetched,
  not shipped**: `fetch_fixture.py` range-reads the 1,712 patch members (428 patches) from W. Stevens' public
  `s4_good_patches.zip` / `s4_bad_patches.zip` (about 18 MB of members, plus about 29 MB of zip directory) and the
  27 region-A CT chunks (about 113 MB) from the public data server, and checks every file against the sha256 recorded in `provenance.json`. Without the
  fetch the fixture tests do not run. `reference_subset.npz` is derived from the June 2026 reference surface
  (CC BY-NC 4.0, see `ATTRIBUTION.md`); it is not an upstream file, so it ships with attribution.
- CT volumes come from the public data server and are used under its terms; W. Stevens' patches from his public upload
  (`community-uploads/will`, report12).
- The whole-scroll solve's input edges, the whole-scroll fit outputs and checkpoints are in a **private store** and are
  not in this repository. Figures that depend on them cannot be regenerated from the repository alone.
- **Network dependencies:** dl.ash2txt.org (patches, CT), github.com (villa), and astral.sh (the uv installer used by
  `phase/arc/setup.sh`).

**Blind decks.** Each deck cited in the report ships with its pre-registration, registered key hash, unsealed key,
responses, scoring script and score (`phase/review/stevens/bdeck*`, `phase/review/s3`, `phase/review/audit_f`), so every
reading can be re-scored from the release. The decks cannot be rebuilt from the release: their builder scripts are
not shipped, and neither are the CT-section images. Three result files over 1 MB are attached to the GitHub release
instead of the tree, with their sha256 values in the release notes: `d1_boundaries.json` (page boundaries) and the
page-1 fix's re-solved `wrap_index.csv` and `unsatisfied.csv`. The page-1 fix's starting index is `community/`'s.

## Release

This tree is built by script from a commit of a private repository, with a name map and a scrub; internal
coordination records, ledgers and session logs are excluded. `SOURCE_COMMIT.txt` names the commit and
`MANIFEST.txt` lists every file with its sha256.

## Licence, attribution, disclosure

- **Our code:** to be released under the **MIT licence** (see `LICENSE`). The licence
  file is added in the release tree. Changes to villa will be submitted upstream separately.
- **Data:** PHerc 1667 (Scroll 4) is the EduceLab-Scrolls dataset; publications cite EduceLab-Scrolls and Parsons et
  al. (2023), arXiv:2304.02084. The CT is used under the data server's terms (including its disclosure terms); the June
  2026 reference surface is CC BY-NC 4.0 (`LICENSE.txt` at its bucket root); W. Stevens' patches carry no licence file.
- **Patches:** grown and aligned by W. Stevens (report12), public upload `community-uploads/will`.
- **Fitter:** villa's Spiral fitter, unchanged, by its authors.
- **AI assistance:** analysis code, experiments and text were produced with AI coding agents under the project owner's direction.
- Machine-generated meshes, including the reference, are not ground truth.
