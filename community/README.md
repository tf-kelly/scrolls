# Scroll 4 winding index for W. Stevens' released patches (release copy)

**In this repository:** `build_s4_index.py` and its two inputs, `wrap_index.csv` and `unsatisfied.csv` (the saved
output of the whole-scroll solve). `build_s4_index.py` checks the sha256 of those two files and writes them out as
`winding.csv` (one row per patch) and `contradictions.json` (the unsatisfied constraints grouped per join). It does not
measure or solve anything. `mkdir -p OUT && python3 community/build_s4_index.py OUT` writes both files into `OUT`;
their sha256 equal the entries in `MANIFEST.sha256`.

**Attached to the Release `sept-submission`** (files too large for the tree):

| File | Bytes | sha256 |
|---|---|---|
| `same_windings.json` | 333,940,314 | `8ab62889d3ea8dad40b79def0b8a97a48d18dee3ae62a81452919d2cebc4fd43` |
| `relative_windings.json` | 38,847,418 | `6e7e7d15378767c084ed1a66a39e1ec6cb6390ff7b953d09d215f21115601214` |
| `MANIFEST.sha256` | 414 | `df000a6be17bc8b7b682f36e054fcee5d805ffbcaf743f1252e1c6bc68c933d4` |
| `solve_edges.json` | 29,214,099 | `6e6eb5f1e52004f3a3b5c9ff16528a03f6cbbe4c33ae515a14e696a324658015` |
| `abs_winding.json` | 31,723,417 | `0393eec11a2f526cd92ae1b94b9c8b4612cd50491301a6a6e8eff3852f2457e2` |
| `d1_boundaries.json` | 1,961,757 | `8634023ac5648e237205f449aca4185435507108a4f2d955af1a7630fa94dd0d` |
| `p1fix_after_unsatisfied.csv` | 1,622,769 | `1dab42ad6fc153ab7acf07e2785fb1b532675bb3f0dd11575bd4536fa4a34859` |
| `p1fix_after_wrap_index.csv` | 1,187,333 | `e077f6da2839e2329903793d717c4565d99de898a18c38d085a3f83eaec7ddfd` |

- The first three belong to this package (described below). `MANIFEST.sha256` lists the package's own README (the
  text below "The package README follows"), the two files `build_s4_index.py` writes, and the two point-collection
  files.
- `solve_edges.json` is the input of the whole-scroll solve: the 174,641 joins over 56,934 patches with each join's
  measurements, and the patch centroids. With it the solve can be rerun instead of repackaged. The scroll-axis file
  it names must sit beside it:

  ```bash
  cp phase/tools/vc_sheet_check/validation/results/v1-12/run/axis_contract_allpatches_zyx.txt DIR/   # DIR holds solve_edges.json
  vc-sheet-check solve --edges DIR/solve_edges.json --spacing-um 134 --compare community/wrap_index.csv --out OUT
  ```

  This reproduces `community/wrap_index.csv` and `unsatisfied.csv` byte for byte (objective 25,553; 87 s in a
  4-CPU container). The measurement that produced `solve_edges.json` (a tiled whole-scroll run of the region check
  over the CT) has no single command in this repository.
- `abs_winding.json` holds fit c's absolute targets: 6 points per patch on 56,926 patches of component 0, each with
  `wind_a` = winding + 13 (the offset from a radius regression on fit a's placed points); `phase/arc/arm_c.sh` reads it.
- The last three are result files over 1 MB, attached instead of committed. They belong at
  `phase/review/stevens/followup/d1_boundaries.json` and
  `phase/tools/vc_sheet_check/validation/results/p1fix/after/{unsatisfied,wrap_index}.csv`. `d1_boundaries.json` holds
  vertex coordinates on W. Stevens' published page surfaces.

`checker_scores.csv` (a whole-scroll per-join checker score) was **not computed** and is not part of the package.

**Counts.**
- The index solved **174,641 joins** (patch pairs).
  - 160,573 carry same-winding constraints (1,283,411 point pairs).
  - 14,067 carry relative-winding constraints (136,039 point pairs).
  - One join (patches 147037 and 147797) lost all of its point pairs to the fitter's loader filter.
- **15,154 joins are left unsatisfied** (23,857 violated constraints); they are listed in `contradictions.json`.

The package README follows.

This folder holds a winding number for each patch in W. Stevens' Scroll 4 patch release. It also lists the joins
where those windings contradict our measurements, and the winding constraints in the point-collection form a Spiral
fitter reads. These are machine-generated outputs. They are not ground truth, and no person has checked them join by
join.

## Source

- **Patches:** grown and aligned by W. Stevens (report12). The public upload is at
  https://dl.ash2txt.org/community-uploads/will/:
  - `s4_good_patches.zip`: 47,797 patches, sha256 `5c5a4865941b05c6fa362a9efa75adbf97db244382fbb7716f4fbf182d7f3fb2`;
  - `s4_bad_patches.zip`: 9,171 patches, sha256 `72f436c57002bf602b3b9b8663abdf2d60617e54e45383d6eb5a7a91b6e8bf6b`.

  The two sets are disjoint, giving 56,968 patches in total. We used them as released. We grew no patches and did not
  use Stevens' 2-D alignments.
- **Patch ids:** `patch_id` is the number `N` in the zip member folder `s4_<good|bad>_patches/patch_N/`.
- **CT:** Scroll 4 (PHerc 1667), scan volume `20231117161658`, 7.91 µm voxels.
- **Coverage:** 56,934 of the 56,968 patches have a winding. The other 34 (33 from the good zip, 1 from the bad zip)
  join no other patch, so the solve cannot place them. 33 of them overlap other patches only where the two surfaces
  coincide, and 1 overlaps nothing. No patch was removed for quality.

## Files

| File | Contents |
|---|---|
| `winding.csv` | One row per patch: `patch_id`, `component`, `winding`, `theta_rad` (56,934 rows) |
| `contradictions.json` | The 15,154 joins where the solved windings violate at least one constraint (23,857 violated constraints) |
| `same_windings.json` | Same-winding constraints, exactly as given to the fitter: 1,283,411 point pairs on 160,573 patch pairs |
| `relative_windings.json` | Relative-winding constraints, exactly as given to the fitter: 136,039 point pairs on 14,067 patch pairs |
| `MANIFEST.sha256` | sha256 of every other file (`sha256sum -c MANIFEST.sha256`) |

`checker_scores.csv` is **omitted**. No whole-scroll, per-join score from our checker (its switch-risk score and flag)
exists in any output we have stored, and we have not computed one for this package. The checker's per-join witness
measurements (verdict, testable points, agreement) are given for the contradicted joins in `contradictions.json`.

`s4_fitted/` (fitted surfaces per winding) is **omitted**. No repeat fit of the scroll with these constraints has passed
its checks yet.

## Frames and units

- Coordinates are full-resolution scan voxels (7.91 µm). In the two point-collection files each point is written as
  `[x, y, z]`, following the point-collection format; z is the slice index along the scroll's long axis. The
  constraints cover z 499–11,001.
- Distances in `contradictions.json` are in micrometres. `theta_rad` is in radians, in [0, 2π).

## How the windings were solved

The solve is reference-free: no published segment or reference mesh enters it.

1. **Joins.** Two patches are joined if their bounding boxes overlap, at least 10 points of one patch lie within
   2 voxels of the other, and at least 20 corresponding points can be mapped between them. Corresponding points on the two surfaces are then compared. A pair whose surfaces are
   everywhere within 1 voxel of each other ("coincident") gives no join. This leaves 174,641 joins.
2. **Measurements on each join:**
   - **crossing count:** for each corresponding point pair more than 1 voxel apart, the number of sheets crossed
     between the two points is counted along a sheet-orientation field computed from the CT. The join's value is the
     median count.
   - **radial separation:** the median separation of up to 10 sampled point pairs along the direction away from the
     scroll axis, divided by a sheet spacing of 134 µm and rounded.
   - **same-wrap rule:** a separation rule from W. Stevens' published work, applied here to our own measurements. If
     the join's maximum separation along the sheet normal exceeds 0.59 × 134 µm = 79.06 µm, the two patches are
     taken to be on neighbouring wraps, in the direction a first solve (crossing counts and radial separation only)
     placed them, or with b one wrap outward of a (+1) where that first solve gave both the same winding. Otherwise
     they are taken to be on the same wrap.
3. **Solve.** One integer winding per patch minimises the total absolute violation over all 514,297 constraints (each
   with weight 1; total 25,553 at the solution). Where several solutions reach that same minimum, a tie-break picks
   the one closest to targets set from each patch's distance from the axis. Each target is that distance relative to
   an anchor patch, divided by the spacing and rounded. The tie-break does not change the minimum.

### Windings, components and the seam

- **`component`:** patches linked by joins. Component 0 holds 56,926 patches. Components 1–3 hold 4, 2 and 2 patches.
  Windings can be compared only within one component.
- **`winding`:** an integer turn number. It increases outwards: the recorded correlation between turn and radius is
  +0.86. It is counted with a seam at `theta_rad = 0`.
- **`theta_rad`:** the angle of the patch centroid about the scroll axis used by the solve (atan2 of y and x, measured
  from the axis point at the centroid's z). The axis is a centre line that varies with z and is not included here.
  `winding` is only meaningful together with this angle and the seam.
- **Turning windings into a layer difference.** For patches a and b,
  - `layer difference = winding_b − winding_a − seam(theta_a, theta_b)`;
  - `seam(ta, tb)` is +1 if the shorter angular path from ta to tb passes 2π → 0 going upward, −1 if it passes 0 → 2π
    going downward, and 0 otherwise.

  Zero means the same sheet. The offsets in `relative_windings.json` equal this layer difference for every point pair,
  and every pair in `same_windings.json` has layer difference 0. We checked both against `winding.csv`.
- **Fractional turn position:** `winding + theta_rad / 2π` changes smoothly across the seam.

## contradictions.json

Each entry in `joins`:

- `patches`: `[a, b]`.
- `constraints`: one entry per violated constraint. Each gives:
  - `constraint`: `crossing_count`, `radial_separation` or `same_wrap_rule`;
  - `value_before_seam`: the measured value, or the rule's target for `same_wrap_rule`;
  - `seam_crossing`: `seam(theta_a, theta_b)`;
  - `required_difference = value_before_seam + seam_crossing`, the required `winding_b − winding_a`;
  - `solved_difference = winding_b − winding_a`;
  - `violation = solved_difference − required_difference`;
  - `weight`: 1.
- `measurements`: the join's own numbers:
  - `crossing_count_median`;
  - `radial_separation_um` and `radial_separation_in_spacings`;
  - `max_normal_separation_um`;
  - `exceeds_same_wrap_threshold` (> 79.06 µm);
  - the witness check behind the crossing count:
    - `witness_testable_points`: the number of point pairs with a countable crossing number;
    - `witness_agreement`: the share of those equal to the median;
    - `witness_verdict`: `same-sheet` (median 0, agreement ≥ 0.8), `switch` (median ≠ 0, agreement ≥ 0.8),
      `ambiguous` (agreement < 0.8) or `untestable` (no countable pair; the crossing count is then null).

A listed join is a place where the index disagrees with at least one measurement. It is not proof that either one is
wrong. Nothing was removed for being contradictory. Every listed join stayed in the solve. All but one are also in the
point-collection files. The exception is the join of patches 147037 and 147797: the fitter-input loader filter's tie
check dropped all of its point pairs.

## same_windings.json and relative_windings.json

These are point-collection JSON (version 1) files. Each collection is named `between_patches__<a>__<b>` and holds two
points, one on each patch.
- In the relative file, point 1 has `wind_a` 0 and point 2 has `wind_a` equal to the layer difference defined above.
- The same file has no `wind_a`: its pairs lie on the same sheet.

Every offset comes from the solved windings, not from the join's own measurements. The constraints therefore agree with
the index by construction, including on the joins listed in `contradictions.json`.

**Build steps.** A converter wrote the files from the index. The points were then snapped onto the patch surfaces
(median shift 0.54 voxels). Finally, the fitter's loader filter for z 499–11,001 dropped 35 tied relative point pairs.

**Version shipped:** the output of the loader filter, which is what the fitter read.

| Stage | same_windings.json | relative_windings.json |
|---|---|---|
| Before snapping | `151eec4ef16d71001759fa995aa18360d396772b9517114bdfd73ea1e39551ce` | `5d34cb0a47ba2c45c25be78adb00795bbc82a738d409e66ac46c3c4bd48f2594` (136,074 point pairs) |
| After snapping | `8ab62889d3ea8dad40b79def0b8a97a48d18dee3ae62a81452919d2cebc4fd43` | `2a1e2abf38c5fe5d80d0fab7a2e5ba4c935985dbd1f70e5d396ec73b561f30be` |
| **After the loader filter (shipped)** | **`8ab62889d3ea8dad40b79def0b8a97a48d18dee3ae62a81452919d2cebc4fd43`** (unchanged) | **`6e7e7d15378767c084ed1a66a39e1ec6cb6390ff7b953d09d215f21115601214`** |

## Licence and credit

- **Data:** the files here are derived from data licensed CC BY-NC 4.0; follow the data server's terms. The CT is used
  under the data server's terms.
- **Stevens' patches:** they carry no licence file. This folder holds his patch ids, numbers computed from his patches,
  and point coordinates on their surfaces, not the patches themselves.
- **Code:** our code is MIT-licensed (see `LICENSE` at the repository root).
- **Citation:** please cite W. Stevens, report12, for the patches.
