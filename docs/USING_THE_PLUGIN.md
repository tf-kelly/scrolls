# Using the VC3D sheet-check plugin

**Single-patch mode ("Tools → Sheet check") is not available in this release.** This manual covers join mode only.

Every step below was run as written, in this order, from this repository's tree (commit dab8f843) on 1 October 2026. `<release>`
is the release tree and `<work>` is any empty working directory.

## 1. What it measures

- **The measurement.** For two patches that touch, the checker takes corresponding points on the two surfaces. It walks
  in a straight line from one point to the other and counts the sheets crossed along the walk, following a sheet
  orientation field computed from the CT.
- **How it is used here.** That count, with other features of the pair, feeds a switch score. The plugin uses this one
  measurement as a join test: a join whose score passes the threshold is flagged.

## 2. Requirements, as observed

| item | observed |
|---|---|
| OS | Ubuntu 24.04.4 LTS container, 4 CPUs, 15 GB RAM, root |
| GPU | not needed: nothing here used one |
| RAM peak | 5.3 GB for the join run (the checker's own `max_rss_mb` 5,310) |
| disk | 4.9 GB for the VC3D source and build; fetched fixture 123 MB (patches 18 MB, CT 105 MB); viewing copies 239 MB; one run's output 77 MB |
| build time | about 24 min wall, with one restart (see 3) |
| join run | 104 s from the menu; 103 s from the command line |

## 3. Build

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r phase/tools/requirements.txt -e phase/tools/vc_sheet_check -e phase/tools/vc_unwrap
bash phase/tools/vc3d_plugin/build_vc3d.sh <work>/villa --apt
```

- **What `build_vc3d.sh --apt` does.** It installs the build packages with apt, clones villa, checks out f4570bf,
  applies `villa_sheet_check.patch` and builds VC3D with cmake and ninja. Run the three commands from `<release>`.
- **The lines that show success.** The log ends with the ninja link line, then
  `built <work>/villa/volume-cartographer/build/bin/VC3D`. The exit code is 0.
- **If the build is interrupted.** Here the container restarted at target 164 of 292. Running the same command again
  printed `patch already applied at f4570bfa6c2b357fd24a17b46f8a43becf87ea8d; continuing` and built the remaining
  128 targets in 452 s.
- **Confirm the plugin loaded.** Start VC3D (see 5). Its standard output prints `vc.sheet_check: action registered`, and
  the **Tools** menu shows **Sheet check** and **Sheet check (joins)**.

## 4. Inputs

- **Patches.** These are W. Stevens' Scroll 4 patches (report12; public upload `community-uploads/will`,
  `s4_good_patches.zip` and `s4_bad_patches.zip`).
  - Format: tifxyz. One folder per patch, `s4_good_patches/patch_N/` or `s4_bad_patches/patch_N/`, holding `x.tif`,
    `y.tif`, `z.tif` and `meta.json`.
  - Join mode also needs pipeline9's `rel.csv`, which lists which patches join.
- **Volume.** A local OME-Zarr directory, given by path, e.g. `<work>/w/cfx/volumes/ct_A_u8.zarr`.
  - The CT is PHerc 1667 (Scroll 4), scan `20231117161658`, 7.91 µm, from the public data server
    (`https://dl.ash2txt.org/full-scrolls/Scroll4/PHerc1667.volpkg/volumes_zarr/20231117161658.zarr`).
- **The quickstart's fixture.** Region A of slab 2, 384³ voxels. It is fetched and sha256-checked from the two public
  sources above:

  ```bash
  python3 phase/data_small/fixture/fetch_fixture.py
  bash phase/tools/vc3d_plugin/inapp/build_inapp_fixture.sh <work>/w .venv/bin/python
  ```

  - The first command took 197 s; the second took 249 s.
  - The second writes `<work>/w/cfx/volumes/ct_A_u8.zarr`, the fixture CT as uint8 in the scan's frame, for viewing.
    It also writes `ct_A_view.zarr` and `umbilicus.json`.
  - The checker itself reads `phase/data_small/fixture/ct.zarr`, as named in the join spec.

## 5. Join mode from the menu

1. **Start VC3D.** This is the exact command used:

   ```bash
   mkdir -p <work>/cfg && printf '[project]\nshow_open_data_catalog_on_startup=false\n' > <work>/cfg/VC3D.ini
   VC3D_CONFIG_DIR=<work>/cfg XDG_CACHE_HOME=<work>/cache \
     VC_SHEET_CHECK=<release>/.venv/bin/vc_sheet_check QT_QPA_PLATFORM=xcb \
     <work>/villa/volume-cartographer/build/bin/VC3D --agent-bridge-name vc3d-m12
   ```

   - `VC_SHEET_CHECK` tells the plugin where the checker is.
   - The `VC3D.ini` line stops VC3D opening its data catalogue at start.
   - `XDG_CACHE_HOME` sets where the outputs go.
   - The session ran on a virtual X display (`Xvfb :97 -screen 0 1920x1080x24`, `DISPLAY=:97`). The
     `--agent-bridge-name` flag was set, but no step below used the bridge: every step was a menu click or typed text.
2. **File → New Project.**
   - In **File name**, type a path ending in `.volpkg.json`, e.g. `<work>/w/cfx/manual.volpkg.json`.
   - Press **Save**.
   - A volume cannot be attached before this step: VC3D answers "Open or create a project first."
3. **File → Attach Volume…**
   - Keep **Local** selected.
   - In the path box, type the volume path, e.g. `<work>/w/cfx/volumes/ct_A_u8.zarr`, and press Enter.
   - At **Tags (comma-separated, optional; e.g. normal3d):** leave it empty and press **OK**.
   - The slice views stay black for now: they open at the scan's centre, which is outside the fixture region.
4. **Tools → Sheet check (joins).** A file dialog opens with **Files of type: Join spec (\*.json)**.
   - In **File name**, give `<release>/phase/tools/vc3d_plugin/join/fixture_A.json` and press Enter.
   - **There are no per-pair fields, and you do not choose two patches.** The join spec names a region, its patch set
     and `rel.csv`. The checker tests every joined pair whose patches meet that region: 666 pairs here.
5. **Wait for the run.** The status bar shows **Sheet check running...**.
   - It finished in 104 s.
   - A **Sheet check** dock then opens on the right with one row per flagged cluster: 15 rows here.
6. **Read a row and jump to it.** Each row reads
   `#<id> suspect_join  z=… y=… x=…  pairs=… patches=…  <area> cm2  switch=<score>`.
   - Double-click a row: the slice views move to that cluster's centre, and the checker's overlay is drawn over the CT.
   - Row #0 is the pair of patches 51179 and 51913, with switch score 0.42.
   - The output files are written under VC3D's cache directory, in `sheet_check/region_<z>_<y>_<x>_<nz>_<ny>_<nx>-<time>/`.
     The plugin prints the full path on its `vc.sheet_check: report …` line.

## 6. Reading the result

- **The number** is the **switch score**: the model's probability that the wrap index changes between the two patches
  of a joined pair.
  - **It is not an error score.** The dock's footer says so: "Flags mark where the index changes, not where it is
    doubtful. "switch" is the switch score, not an error estimate."
- **The threshold** is 0.3293. The fixture's join spec uses model v1, and a pair at or above 0.3293 is flagged.
  - The checker's default model, v2_noz, uses 0.516.
  - Here 130 of 666 pairs were flagged, in 15 clusters.
- **There is no PASS or FAIL per join.** A flag says "the index changes here". It does not say "this join is wrong".
- **Held-out accuracy** comes from the claims register (row F28), on held-out Scroll 4 z-bands: 84,887 pairs, 5,518 of
  them switches.

  | model | threshold | precision | recall |
  |---|---|---|---|
  | v1 | 0.3293 | 0.490 | 0.884 |
  | v2_noz | 0.516 | 0.565 | 0.872 |

  - So about half of the flags are not switches. This uses labels derived from a machine-assisted reference mesh, not
    ground truth.

## 7. Batch use

- **The plugin's own test, without the VC3D window:**

  ```bash
  bash phase/tools/vc3d_plugin/run_join_test.sh <release>/.venv/bin/vc_sheet_check
  ```

  - This ran in 113 s and ended `ALL PASS 0 failure(s)`, with 15 dock rows for 15 clusters and the jump-to on row 0 at
    cluster 0's centre.
  - Its header says it needs g++ and Qt 6 (Core, Widgets). Here `build_vc3d.sh --apt` had already installed them.
- **The checker alone**, with the same arguments the menu used:

  ```bash
  .venv/bin/vc_sheet_check --region 4224 2560 640 384 384 384 \
    --patches phase/data_small/fixture/patches.zip --rel phase/data_small/fixture/rel.csv \
    --volume phase/data_small/fixture/ct.zarr --wrap-index phase/p1page/p1b_q3c_k.csv \
    --patch-table phase/data_small/fixture/patches.csv \
    --risk-model phase/tools/risk_model/risk_model_v1.joblib --out <work>/cli_out
  ```

  - This exited 0 in 103 s.
  - Its `switch_risk.csv` is byte-identical to the menu run's.
- **`switch_risk.csv` columns:**

  | column | meaning |
  |---|---|
  | `patch_a`, `patch_b` | the pair |
  | `risk` | switch score |
  | `flagged` | 1 if `risk` ≥ the threshold |
  | `sep_um` | the pair's separation in µm |
  | `contact` | 1 when `sep_um` < 50 (true for all 666 rows here) |

- **`report.json`:**
  - `counts`, e.g. `pairs_scored` 666, `pairs_flagged` 130, `pairs_flagged_contact` 34;
  - `clusters`, each with `id`, `kind`, `n_pairs`, `n_patches`, `area_cm2`, `centroid_zyx`, `bbox_zyx`, `patches`,
    `pairs` and `max_risk`;
  - `resources`, with wall time and peak RAM.
- **`overlay.zarr`** is the overlay the plugin draws.

## 8. Known limits and errors seen

- **"Open or create a project first."** This appears if you attach a volume with no project open. Fix: File → New
  Project first.
- **Black slice views after attaching the fixture volume.** The view opens outside the data. Fix: double-click a dock
  row.
- **"Low disk space: … GiB free; remote Zarr cache growth is paused."** This banner showed with 6.3 GiB free. It
  pauses remote downloads only; this run used local volumes and was unaffected.
- **Contact pairs.** 34 of the 130 flagged pairs are contact pairs (`sep_um` < 50). The checker's contract
  (`phase/tools/CONTRACT.md`) records that the checker has no working measurement in this regime (contact recall 0.017
  at precision 0.85).
- **The test script's header understates the cost.** `run_join_test.sh`'s header says "~4 min, < 2 GB". Measured:
  113 s and a checker peak of 5.3 GB.
- **Interrupted build.** Re-run the same `build_vc3d.sh` command; it resumes (section 3).
- **The menu and the command line agree.** The menu run's `switch_risk.csv`, `recomputed_features.csv` and
  `cleaned_patches.csv` are byte-identical to the command-line run's. Compare menu runs with that.
