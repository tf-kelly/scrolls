# Integration fixture (contract v1, §6)

This fixture is a small, committed test case for every implementation of the contract. It is **not an evaluation set.** The
risk model was trained on all of slab 2, these pairs included, so fixture flags are in-sample. Use it to check formats,
conventions and reproduction, never to quote performance.

Fetch the third-party parts first: `python3 phase/data_small/fixture/fetch_fixture.py` (W. Stevens' patch members
into `patches.zip` and the region-A CT chunks into `ct.zarr`, each checked against the sha256 in `provenance.json`).
The rebuild script `build_fixture.py` needs private inputs and is not in this tree.
Test: `python3 phase/tools/test_fixture.py [--outputs DIR]`.
Example of correct §4 outputs: `python3 phase/tools/example_outputs.py DIR` (region A, built from golden values).

## Regions

Both regions are in X3 slab 2 of PHerc1667 (Scroll 4), scan `20231117161658` at 7.91 µm, in L0 voxels (z, y, x).
Both are 384³ (3.04 mm) and aligned to the scan's 128³ chunks.

| region | z | y | x | CT | θ (about the patch-centroid axis) | X6 pairs with a midpoint inside | adjacent |
|---|---|---|---|---|---|---|---|
| A_rich | 4224–4608 | 2560–2944 | 640–1024 | yes | ≈ 130° | 397 | 89 |
| B_cut | 4224–4608 | 1664–2048 | 2432–2816 | no | −10° … 18° (crosses θ0) | 258 | 9 |

Why these regions:
- A is the chunk-aligned 384² crop with the most X6-adjacent pairs at this z. The ranking came from `x6b_points.npz`
  midpoints.
- B is the best crop that straddles the θ0 cut. It tests cut handling in wrap numbering.
- CT for both would have exceeded the 200 MB limit, so B carries geometry only.

## Files

| file | what | convention |
|---|---|---|
| `ct.zarr/` | CT of region A. Level 0 holds the scan's own uint16 values; level 1 is a 2× mean. | OME-Zarr v2, axes z, y, x, 128³ chunks, blosc-zstd. `translation` = origin × 7.91 µm. |
| `patches.zip` | The 428 patches whose bbox meets A (231) or B (197), in Stevens' tifxyz layout. | Members are byte-identical to `s4_good_patches.zip` / `s4_bad_patches.zip` (SHA-256 in `provenance.json`). tifxyz holds x, y, z voxel coordinates; invalid cells ≤ 0. |
| `patches.csv` | `phase/x1/patches.csv` rows for those patches, plus `regions`. | bbox and centroid in **x, y, z** order, as the source |
| `x6_pairs.csv` | `phase/x6/x6b_pairs.csv` rows among fixture patches (991: 122 adjacent, 847 same-wrap, 22 unresolved), plus `region_of_midpoints`. | as source |
| `x6_points.npz` | X6's evaluated point pairs for those rows: `PA`, `PB` and `pair` (row index into `x6_pairs.csv`). | **x, y, z** voxels, float32 |
| `rel.csv` | P9's pipeline9 `rel.csv` rows among fixture patches. | P9 format |
| `pipeline9_badpatches_b.csv` | pipeline9 mode-b flagged patches among fixture patches. | one id per line |
| `pair_features.csv` | `phase/x8/pairs_dataset.csv` rows among fixture patches (894). | as source |
| `reference_subset.npz` | ×4-upsampled reference vertices within 200 µm of a fixture patch point (828,517): `xyz`, `u` (grid column, for the P1f defect test) and `t_ref` (continuous reference turn, RefMesh convention, S_REF = +1). | **x, y, z** voxels, float32. Licence CC BY-NC 4.0. |
| `provenance.json` | Sources, hashes, counts and golden summary. | |
| `golden/wrap_index.csv` | Q3c reference-free wrap index per patch (`p1b_q3c_k.csv`), with `k_ref` for scoring. | +1 = outward. The gauge is per component. |
| `golden/switch_risk.csv` | Risk model v1 on `pair_features.csv`: `risk`, `flagged` (≥ 0.3293), `x6_truth`. 154 of 894 flagged. | in-sample |
| `golden/defects.csv` | P1f reference-defect test at each X6 pair's median point-pair midpoint: 888 ok, 1 duplicated, 102 displaced. | |
| `golden/pages_metrics.json` | Pages and M1/M2/M3 for (i), (ii) and (iii-rf) on the fixture's joins: per-patch-layer and X6 labellings, X6 with defects excluded, and per-point M2. | page threshold 0.1 cm² (below) |

**Page threshold on the fixture is 0.1 cm²,** not the contract's 1 cm². Real pages are larger than a 3 mm crop. Inside
the crops no (ii) or (iii-rf) component reaches 1 cm²; the largest is 0.54 cm². Implementations must take the
threshold as a parameter. The contract value is unchanged.

Sanity checks at build time:
- The modal `floor(t_ref)` over each patch's points equals X7's committed per-patch `k_ref` for 99.5 % of 426
  patches.
- 98.8 % of patch points (median over patches) have reference surface within 60 µm.

## Licences and provenance
- CT: Vesuvius Challenge open data (PHerc1667, `dl.ash2txt.org`), under the Vesuvius Challenge data terms.
- Reference surface: CC BY-NC 4.0 (`LICENSE.txt` at the bucket root).
- Patches: W. Stevens' community upload (`dl.ash2txt.org/community-uploads/will/`). No licence file is in the zip.
  They are used here exactly as earlier stages used them (X1 onward).
- `patches.zip` and the CT chunks are not in this tree; `fetch_fixture.py` fetches them from the public sources.

## Git
`.gitignore` excludes `*.zip` and `*.zarr/` repository-wide. It is left unchanged: `PACKAGE-MANIFEST.json` hashes it.
These fixture files were force-added (`git add -f`), following the precedent in `phase/OWNERS.md` for small outputs.
A rebuild must be force-added the same way, and only as a new recorded version: the golden files here are frozen.


## v1.1 (additive, 2026-09-27; contract Amendment 4 §A4.4)

v1 files are unchanged. New:
- `golden/expected_cross_turn_clusters.json`: every rel.csv join (flip1 excluded) that X6 labels **adjacent** with
  an evaluated-point midpoint inside region A: **30 joins in 13 clusters** under §4.1's rule
  (single linkage at 50 µm on the joins' evaluated points).
  - This is the **reference side**: X6 labels, from one machine-made mesh. It is not ground truth.
  - 11 of the 30 are contact-regime joins (< 50 µm).
  - 23 of the 30 are flagged by the switch score. This is in-sample and is not a performance
    number.
- `golden/report.json`: `example_outputs.py`'s region-A report (31 suspect-join and 21 wrong-turn clusters). The `git` field is blanked.
- `build_golden_v1_1.py` rebuilds both. `test_fixture.py` G5 checks that the expected clusters reproduce.

Expected clusters (coordinates are zyx scan voxels, §1 and Amendment 4 §A4.3; bbox is over the evaluated points,
PA, PB and midpoints since v1.3, which may extend beyond the crop):

| id | X6-adjacent joins | centroid (z, y, x) voxels | bbox min → max (z, y, x) | θ° | contact (< 50 µm) | flagged by switch score |
|---|---|---|---|---|---|---|
| 0 | 14 | (4304.68, 2802.44, 882.39) | (4195.33, 2710.24, 724.27) → (4477.55, 2933.1, 1083.83) | 128.4 | 5 | 11 |
| 1 | 4 | (4232.47, 2652.58, 652.08) | (4194.05, 2607.85, 584.63) → (4327.45, 2711.0, 692.0) | 139.9 | 2 | 3 |
| 2 | 2 | (4241.56, 2792.96, 819.34) | (4191.05, 2757.31, 765.43) → (4341.64, 2828.95, 899.34) | 130.7 | 0 | 2 |
| 3 | 1 | (4527.31, 2664.97, 915.74) | (4523.0, 2655.03, 901.39) → (4530.78, 2673.87, 930.93) | 131.7 | 1 | 0 |
| 4 | 1 | (4379.03, 2787.83, 972.73) | (4373.66, 2767.35, 950.96) → (4382.66, 2833.99, 1029.27) | 125.6 | 1 | 1 |
| 5 | 1 | (4535.58, 2949.78, 1103.11) | (4480.29, 2911.0, 1001.51) → (4588.0, 2977.77, 1175.87) | 116.8 | 0 | 1 |
| 6 | 1 | (4381.15, 2809.99, 956.43) | (4381.14, 2808.98, 956.02) → (4381.16, 2811.0, 956.84) | 125.7 | 1 | 0 |
| 7 | 1 | (4258.68, 2839.63, 999.84) | (4240.5, 2827.42, 978.37) → (4292.13, 2856.02, 1015.21) | 123.1 | 0 | 1 |
| 8 | 1 | (4583.19, 2829.93, 836.84) | (4560.65, 2809.64, 815.19) → (4601.1, 2846.68, 861.79) | 129.5 | 1 | 0 |
| 9 | 1 | (4518.1, 2807.27, 791.67) | (4461.27, 2738.04, 722.88) → (4576.32, 2871.26, 876.92) | 131.6 | 0 | 1 |
| 10 | 1 | (4246.81, 2636.0, 630.37) | (4225.46, 2600.67, 592.47) → (4280.77, 2659.39, 658.18) | 141.0 | 0 | 1 |
| 11 | 1 | (4219.8, 2715.3, 710.39) | (4160.23, 2671.0, 656.0) → (4271.11, 2760.0, 771.62) | 136.3 | 0 | 1 |
| 12 | 1 | (4527.76, 2806.87, 780.43) | (4474.16, 2738.93, 670.51) → (4641.92, 2855.65, 840.84) | 132.0 | 0 | 1 |

**zarr pin.** The tools now run under `zarr==2.18.7` (`phase/tools/requirements.txt`). `build_fixture.py` writes
the CT with the zarr 2 API. Rewriting the CT with it gives **identical decoded values** at both levels, but different
compressed chunk bytes in 31 of 35 files: the committed `ct.zarr` was written under zarr 3.1.6. G1 checks decoded
values, so it holds under either library. The committed files stay as they are.
**VC3D:** `ct.zarr` carries a non-zero OME translation, so VC3D cannot use it as its base volume as committed (the plugin's
reading of `ZarrChunkFetcher.cpp:757`). The plugin's in-app tests used a relocated view.

## v1.2 (2026-09-27; contract Amendment 5 §A5.4–A5.5)
- `golden/report.json` `counts.joins` is corrected from **376 to 318**. The example writer had added page joins and
  flagged X6 pairs; the contract definition is unordered `rel.csv` pairs among the region's patches minus
  flip = 1-only pairs.
- Nothing else in the file changed (one-line diff).
- `test_fixture.py --outputs` now requires a region-A run to reproduce the golden clusters and join count.

## v1.3 (2026-09-27; contract Amendment 7 §A7.2): reconciled with the checker CLI

**The one cluster.** The checker CLI (`vc-sheet-check fixture --out OUT`) finds 51 clusters on region A;
v1.1/v1.2 had 52.
- The difference is pair **(148436, 150217)**. The old golden kept it as a singleton suspect-join cluster; the checker merges
  it into the 32-pair cluster, making 33.
- Its nearest PA/PB point is **6.97 voxels** from that cluster, over the 6.32-voxel (50 µm) threshold. Counting
  midpoints, the gap is **4.84 voxels**.
- **The checker is right.** §4.2 defines a flagged pair's evaluated points as "PA, PB and their midpoint". The fixture's example
  writer used that set for the overlay but only PA/PB for clustering. The same fix is applied to the expected
  X6 clusters: still 13 clusters over the same 30 joins, with centroids recomputed above.
- Where §4.1 was silent, the checker's definitions are adopted (Amendment 7 §A7.2):
  - suspect-join `area_cm2`;
  - `max_risk` = null for wrong-turn clusters;
  - `areas_cm2.flagged_suspect`, `wrong_turn` and `cleaned_kept`.
- **Result:** `golden/report.json` equals the checker CLI's output on region A in counts, all five areas and all 51 clusters,
  field for field (θ to 0.01°). The validator now checks all of these.

## v1.4 (2026-09-27; contract Amendment 10 §A10.2): overlay region
- **Problem (plugin review R7).** The overlay was written only inside the 384³ analysis crop. On v1.3, **26 of 51** cluster
  centres lie outside it, and **13** clusters have no overlay voxel anywhere in their bbox. Jumping to those showed no
  flag. This was 26 of 52 on v1.1 and is 26 of 51 on v1.3.
- **Change.** `golden/report.json` gains `overlay_region`: origin (3712, 2176, 384) and shape (1408, 896, 1152) zyx.
  That is the bbox of the 507 scored pairs' PA/PB/midpoints and of the wrong-turn-tested vertices, plus 380 µm,
  snapped to 128. `amendments` gains 10.
  - Nothing else changed: clusters, counts, areas and metrics are identical to v1.3.
  - `example_outputs.py` writes the overlay over `overlay_region`. Inside the crop it differs from v1.3's overlay only
    at 52 border voxels (0 or 1 → 2). These are wrong-turn vertices just outside the crop, whose one-voxel dilation
    now reaches in.
- **Validator:** cluster centres inside `overlay_region`, a flag voxel in every cluster's bbox, and region A's
  `overlay_region` equal to the golden. `--pre-a10` reports these as PENDING for branches not yet on A10.
- **Cost:** the example writer now peaks at 4.5 GB RSS and takes 53 s wall. The overlay region is 1.45 G voxels,
  written sparsely (112 level-0 chunks stored).
- **VC3D note (A10.1):** the committed `ct.zarr` has a non-zero translation. VC3D's local reader ignores it and would
  draw it at voxel − origin; it is not rejected. The plugin's tests open it through a relocated view.
