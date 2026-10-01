# Scale add-on: placed area, the whole-surface picture and ink for the whole-scroll fit

This add-on reads the two finished whole-scroll fits (`$DATA/vc_arc/out/arm_a/` and `arm_b/`: `final.ckpt`,
`run_small.tgz`, `config.json`) and runs four GPU jobs. Every job writes under `$DATA/vc_arc/scale/out/`.

| Job | What it does |
|---|---|
| `scale_place.sh` | Placed area of the traced patches on each fit, split by sheet-separation regime; the arm (a) vs arm (b) comparison |
| `scale_flatten.sh ARM` | The whole fitted surface of one arm as one tifxyz, then flattened |
| `scale_render.sh ARM` | The flattened surface rendered as CT texture at pyramid level 2 (about 32 µm per pixel), uncropped; a support map; two full-resolution crops |
| `scale_ink.sh [ARM]` | Ink along the surface: (i) from a 3-D ink-prediction volume, whole surface; (ii) the ink model on one fixed band |

- **No C++ tools are needed.** Everything is Python in the fit jobs' venv (`$DATA/vc_arc/env`).
- The villa code used is `villa/spiral-fitting` at the pinned commit, unchanged.
- A pinned subset of villa's `lasagna` ships here (see `LASAGNA_PIN.json`).
- The fitting code is not changed.

## Before you start

- `setup.sh` from the fit bundle has run (`SETUP OK`), so `route.txt`, `env/` and `villa/` exist.
- Both fits are `DONE`: `$DATA/vc_arc/out/arm_a/DONE` and `arm_b/DONE`. `scale_place.sh arm_a` can run before
  arm (b) is done.
- `tranche_s4_whole/dataset.tgz` is still in place. The jobs unpack it to `$SCRATCH`.
- For the render and ink jobs, set these in the shell you submit from. The values are sent separately, never
  written into these files.

  | Variable | Needed by | Meaning |
  |---|---|---|
  | `CT_ZARR` | render, ink | Base URL of the 7.91 µm OME-zarr volume (the directory that holds `0/`, `1/`, `2/` …) |
  | `INK_ZARR` | ink (i) | URL of the 3-D ink-prediction array (a bare zarr v2 array, axes stored y, x, z) |
  | `INK_CKPT_URL`, `INK_CKPT_SHA256` | ink (ii) | The ink model's weights and their sha256 |
  | `INK_METRICS_MODEL` (optional) | ink | Model id for villa's `get_ink_metrics.py`. Needs internet for pip and the model download. |

- Compute nodes read the volumes over HTTP, chunk by chunk, near the surface only.
- Chunks are cached under `$DATA/vc_arc/cache/zarr/`, so a resubmitted job does not fetch them again.

## Commands, in order

**0. Login node: unpack and check (seconds).**
```sh
cd $DATA && sha256sum vc_scale_bundle.tar && tar -xf vc_scale_bundle.tar \
  && (cd vc_arc/scale && sha256sum -c --quiet SHA256SUMS && echo "scale bundle ok")
cd $DATA/vc_arc/scale && for j in place flatten render ink; do sbatch --test-only scale_$j.sh arm_a; done
```
- Expected: `scale bundle ok`, then one `sbatch: Job … to start at …` line per script.

**1. Placed area, both arms (about 0.5 h).**
```sh
cd $DATA/vc_arc/scale && sbatch scale_place.sh
```
- The log (`vc_scale_place_NNN.out`) shows, per arm:
  - `patch satisfaction: 56,934 patches, … quad centers` three times, for the 1, 2 and 6 voxel tolerances;
  - `tol 1 vox: placed … of … cm2`.
- Then comes the table from `out/place/place_table.md` and one line `placed@1vox arm_a=…/…cm2 arm_b=…/…cm2`.
- Last line: **`PLACE OK`**.

**2. Flatten each arm (two jobs, which can run at once; estimate 0.5–2 h each).**
```sh
sbatch scale_flatten.sh arm_a && sbatch scale_flatten.sh arm_b
```
- Expected in the log:
  - `[scale] windings L..H (villa default 10..130, capacity 160)`;
  - `[spiral] reconstructed winding …` lines;
  - `[lasagna] …` progress lines.
- Last line: **`FLATTEN OK`**.

**3. Render each arm (CPU-heavy; estimate 0.5–1.5 h each).**
```sh
export CT_ZARR='<CT base URL>'
sbatch scale_render.sh arm_a && sbatch scale_render.sh arm_b
```
- Expected in the log:
  - `picture: grid … step 20.0 vox -> 4.0 vox/px`, then `tile k/n` lines;
  - `support: KD-tree over … quad centres`;
  - a JSON line with `shape`, `pixel_um` ≈ 31.64 and `unavailable_px`.
- Last line: **`RENDER OK`**.

**4. Ink, arm (a) (estimate 2–4 h).**
```sh
export CT_ZARR='<CT base URL>' INK_ZARR='<ink array URL>' INK_CKPT_URL='<weights URL>' INK_CKPT_SHA256='<sha256>'
sbatch scale_ink.sh arm_a
```
- Expected in the log:
  - `ink (i): 3-D ink volume, whole surface, 4 vox/px`;
  - `ink (ii): 65 layers in z band 5622:5878`;
  - `tiles …/…`;
  - a JSON line with `spearman_rho`.
- Last line: **`INK OK`**.

**4b. Quilt, arm (a) (after step 2; CPU-heavy plus one flatten; estimate 1–2 h).**
```sh
export CT_ZARR='<CT base URL>'
sbatch scale_quilt.sh arm_a
```
- **Inputs:**
  - the patches from `tranche_s4_whole/dataset.tgz`;
  - the checker's winding index, shipped as `flags/wrap_index_whole.csv`;
  - its unsatisfied terms, `flags/unsatisfied_whole.csv`;
  - the axis (`umbilicus.json`);
  - the arm's fitted surface from `out/flatten/<arm>/source/`.
- `WRAP_INDEX=` and `FLAGS=` override the index and the flags.
- Expected in the log:
  - `quilt build`;
  - `pass 1/2: …/56926 patches`;
  - one line per winding: `w +k: R … vox, trace … fill … conflict … cm2`;
  - the totals row;
  - `quilt flatten`, the `[lasagna]` lines, `quilt render`.
- Last line: **`QUILT OK`**.

**4c. SNAP, arm (a): post-processing on the quilt (CPU only; after steps 2 and 4b).**
```sh
export CT_ZARR='<CT base URL or local path>'
sbatch scale_snap.sh arm_a
```
- What it does:
  - it moves the quilt's fill cells onto the CT layer beside them;
  - traces are untouched;
  - villa is not run;
  - the rule is in `PLAN.md` addendum 7.
- If `out/quilt/arm_a/build_snap/` does not exist yet, it first re-runs the quilt build there, with the same inputs.
  This also writes each winding's r and r_fit. The flatten and render of the quilt are not touched.
- It reads level-1 CT. `SNAP_LEVEL`, `SNAP_HELDOUT_MAX` (default 3,000,000) and `SNAP_MEM_CHUNKS` (default 4,000
  chunks of 4 MB) override the defaults.
- Expected in the log:
  - `quilt build for snap` (only if needed), then the per-winding `w +k: R … trace … fill …` lines;
  - `… windings; excluded (index unreliable, addendum 4b): [...]`;
  - `fill cells …, held-out trace cells …`;
  - `held-out w +k: … cells profiled` for each winding;
  - `tau = … (…)`;
  - `fill w +k: … cells, accepted peaks …`;
  - `w +k: snapped …/…; E trace …, fill before …, after …`;
  - the SNAP table.
- Last line: **`SNAP OK`**.
- **Per winding, as completed:**
  - `out/quilt/arm_a/snap/windings/w±KKK_pass1.npz` (before the separation guard);
  - then `w±KKK.npz` and `.json` (final).
  - A timeout still leaves the finished windings.
- Outputs: `snap.json` and `snap_table.md` (the held-out accuracy and coverage table, P2, P3, P5, and the control).
  They are small and go in the download.
- **Time: unmeasured on the cluster.** It is sent with the slab-2 test result. The whole
  scroll has about 18× the fill of slab 2.

**5. Login node: pack the download set (numbers, coarse images, flattened tifxyz).**
```sh
bash $DATA/vc_arc/scale/pack_scale.sh
```
- It writes `scale_return_arm_a.tgz`, `scale_return_arm_b.tgz` and `scale_return_common.tgz`, printing each one's
  files, MB and sha256. It warns if an arm exceeds 500 MB.
- Last line: **`PACK OK`**.
- Full-size renders, per-quad arrays, band layers and the lasagna model stay in `$DATA/vc_arc/scale/out/`.

A job that fails ends with `<STAGE> FAILED: <reason>` and keeps its log in `out/logs/`. Resubmitting the same
command is safe: each stage rewrites only its own output folder.

## Expected sizes (whole scroll, per arm)

These are measured on slab 2 and scaled × 13.7 by z-extent. They are estimates, not measurements of the whole
scroll.

| Stage | On `$DATA` (stays) | In the download set | Download set, total |
|---|---|---|---|
| place | `quad_cn.npy` ≈ 5.6 GB, `quads.npz` ≈ 0.75 GB | `place.json`, `pairs.npz` (≈ 15 MB), `patch_ids.txt` | ≈ 15 MB |
| flatten | lasagna `model.pt` ≈ 0.8 GB, `source/` ≈ 0.2 GB | `flat.tifxyz` x/y/z/meta, `flatten.json`, `source/manifest.json` | ≈ 110 MB |
| render | `texture.tif` ≈ 0.85 GB, `support_dist.tif` ≈ 0.6 GB, full-size PNGs ≈ 0.9 GB | `texture_folded.jpg` ≈ 100 MB, `overlay_folded.jpg` ≈ 85 MB, `support.png` ≈ 25 MB, `crops/` ≈ 10 MB, `picture.json`, `overview_small.jpg` | ≈ 220 MB |
| ink (arm a only) | band `layers/` ≈ 20 GB, `pred.tif` and `ink_zarr_band.tif` ≈ 1.3 GB each, whole-surface `ink_raw.tif` ≈ 0.3 GB | `ink_overview.jpg` ≈ 80 MB, `*_preview.png` ≈ 20 MB, `*.json` | ≈ 100 MB |

- **arm_b:** ≈ 345 MB. **arm_a:** ≈ 445 MB. **common** (tables, logs): < 10 MB.
- Chunk caches: see *Resources and knobs*.

**Quilt (arm a):** it gets its own download tarball, `scale_return_quilt_arm_a.tgz`, of about 350 MB.
- It contains the build JSON and table, the flattened x/y/z, the folded JPEGs, `support.png` and the crops.
- The per-winding 4-voxel tifxyz (about 1.5 GB) and the concatenated 20-voxel tifxyz stay on `$DATA`.

## Output files

**`out/place/`**

| File | Contents |
|---|---|
| `place_table.md` | Placed area (cm², 3-D quad area from the patch grids, summed over patches) within 1, 2 and 6 voxels, by regime (`<25`, `25-50`, `>=50` µm, `none`), per arm, with the gap a − b. Also the unique-surface area and the arbiter table. |
| `place_summary.json` | Everything in the table. Also `flag_split`: the placed area by patch class (flagged = in the checker's `unsatisfied.csv`, shipped as `flags/unsatisfied_whole.csv`; `FLAGS=` overrides it) × regime, in two variants (all unsatisfied terms; switch-verdict only). Also: the arm (a)/(b) disagreement areas (a only, b only, both, neither) by regime; the 6-voxel cross-check against the fit's own `satisfied_fitted.json` (from `run_small.tgz`); the arbiter conventions. |
| `<arm>/place.json` | One arm's totals: tolerances, regimes at radius 64 and 256 voxels, snapped winding range, dr, wall time, GPU memory. |
| `<arm>/quads.npz` | Per quad, in villa's packed order: placed bits, 3-D area, regime codes, snapped winding. |
| `<arm>/quad_cn.npy` | Quad centres and normals, used by the render job's support map. Large; not packed. |
| `<arm>/pairs.npz` | The fitted winding value at both points of every same- and relative-winding pair. |

**`out/flatten/<arm>/`**

| File | Contents |
|---|---|
| `source/` | The unflattened combined surface (all exported windings), with villa's `manifest.json` |
| `flat.tifxyz/` | The lasagna-flattened surface, trimmed to its valid cells |
| `flatten.json` | Winding range (villa default and exported), shapes, wall times |

**`out/render/<arm>/`**

| File | Contents |
|---|---|
| `texture.png` / `texture.tif` | The whole surface, one pixel ≈ 31.6 µm, uncropped. Black is either no surface or unavailable CT; the two are counted separately in `picture.json`. |
| `support.png` | Per pixel, the distance to the nearest traced patch along its normal. Green: ≤ 1.5 voxels (on a trace). Orange: ≤ 8 voxels (near, off by a few voxels). Red: no trace within 16 voxels. |
| `overlay.png` | Texture with the support colours. `overview.png` is the same image folded into 8,192-pixel rows; `overview_small.jpg` is a small preview. |
| `crops/on_sheet_L0*.png`, `crops/off_sheet_L0*.png` | Full-resolution crops (2,048² pixels). The first is the window with the highest on-trace share. The second has the lowest on-trace share among windows where traces exist. |
| `picture.json` | Pixel size, handedness and flip record, stretch, support shares, on-trace share per column band (where the bad bands are), crop positions |

**`out/ink/<arm>/`**

| File | Contents |
|---|---|
| `zarr_whole/ink.png`, `ink_overview.jpg`, `ink/…jpg` | The 3-D ink volume along the whole surface: maximum over ±2 voxels, divided by the 95th percentile. `ink/` holds the strip tiles named the way villa's metrics script reads them. |
| `band/layers/00..64.tif`, `mask.tif` | The band's 65 layers: layer k at k − 32 voxels along the inward normal, uint8 = CT / 257. Uncompressed and memory-mappable; the `*_preview.png` files are subsampled views. |
| `band/ink_zarr_band.tif`, `_preview.png` | The ink volume on the same band pixels |
| `model/pred.tif`, `pred_preview.png`, `run.json` | The ink model's prediction on the band |
| `model/concordance.json` | Spearman ρ between the model and the ink volume over 64-pixel tiles |
| `metrics/` | Only if `INK_METRICS_MODEL` is set: villa's `get_ink_metrics.py` output |

**`out/quilt/<arm>/`**

| File | Contents |
|---|---|
| `build/quilt_table.md`, `quilt.json` | Per winding and in total: trace-covered, filled and conflict area (cm²), and conflict area over all patches (flagged included). Also the geometric-conflict pairs against the checker's flagged joins: precision, recall, and recall among co-located pairs. |
| `build/windings/w±KKK/{x,y,z,label}.tif` | One surface per winding at 4 voxels. Label 1 = trace, 2 = fill, 3 = conflict (left empty), 0 = none. |
| `build/concat.tifxyz`, `concat_label.tif`, `labels_pts.npy` | All windings side by side at 20 voxels (for the flatten), and the labels for the support map |
| `flatten/flat.tifxyz` | The lasagna-flattened quilt |
| `render/…` | As for the arms. Support colours: green trace, blue fill, magenta conflict, red none. Crops: the most-trace window (`trace_L0`) and the most-fill window (`fill_L0`). |

**How the quilt is built**, per winding w of the checker's index (component 0):
- The per-vertex winding is k + cross(θ_patch, θ_vertex), the checker's own cut convention.
- Flagged patches are dropped.
- Patches are upsampled ×2 and binned by (arc at the winding's median radius, z) into 4-voxel cells, one mean r per
  patch per cell.
- A cell with ≥ 2 patches whose radii differ by more than 0.6 × 134 µm is a conflict and stays empty. Otherwise its
  radius is the mean of the patches' means.
- An empty cell takes the fitted sheet nearest the traces, carried from the nearest trace cell. It adds a membrane
  (harmonic) interpolation of the trace−fit residual that is zero 64 cells from any trace, so seams do not step.

## Resources and knobs

- Each job asks for 16 CPUs and 128 GB.
- The render and ink jobs run their sampler in `WORKERS` processes (default: CPUs − 1). Each process caches at most
  `VC_SCALE_CACHE_MB` of decoded chunks (default 1536).
- `CROP_PX` (default 2048) sets the size of the full-resolution crops.
- `INK_STEP` (default 4 voxels per pixel, about 32 µm, the scale the ink-coverage model expects) sets the pixel size
  of the whole-surface ink route.
- `INK_STRIDE` (default 32) sets the model's tile stride.
- The chunk caches are about 4 GB at level 2 and about 41 GB for the ink array. The level-0 band is about 25 GB for
  a 256-voxel band. All of them live under `$DATA/vc_arc/cache/zarr/` and can be deleted after the jobs.

## Conventions

- Arrays are z, y, x. tifxyz stores x, y, z in level-0 voxels. The voxel is 7.91 µm.
- **Normals** point inward (towards the umbilicus), with one sign per connected component, voted over vertices more
  than 500 voxels from the axis.
- **Handedness** = sign(raw grid normal · inward). A surface with handedness −1 is flipped left–right at the source,
  and `picture.json` records it.
- **Placed** means villa's satisfaction test at that tolerance: the quad centre lies within the tolerance of the fitted
  surface of the winding it snaps to. It is geometric agreement, not proof that the winding is the right one.
- **Regime** of a quad: the separation (|p₁ − p₂| × 7.91 µm) of the nearest relative-winding pair on its patch within
  64 voxels; otherwise `none`.
- **Unavailable volume data** is never drawn as dark papyrus. It is counted separately.
