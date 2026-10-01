# F3, F2 (page 1), F1: SessA's parts of the coordinator's 14:38 / 15:05 audit items (SessA instruction, SessA instruction)

Committed before any F-item computation. Order as ruled: F3 → F2 page 1 → F1. Index throughout: SessA-15's Scroll 4
whole-scroll index (`results/v1-15/whole/wrap_index.csv`, 1c0b7d30…, s = +1, axis `results/v1-12/run/axis_contract_allpatches_zyx.txt`),
re-solved with `vc-sheet-check solve --spacing-um 134` from SessA-12's edges (6e6eb5f1…), which reproduces it exactly (P1FIX).

## The checker, and its power (applies to F1 and F2)
`vc_sheet_check --segment` reports power = the SessA-4 (b) calibrated sensitivity, 0.17 (95 % CI 0.08–0.32), whenever the
run's pair density is at or above the calibration density, which dense mode always is. No setting raises it: the
calibration measured sensitivity to planted 2 mm jumps, and the only knob (`--pairs-per-cm2`) can lower density, not
sensitivity. **So "full power" is not reachable with this checker.** The setting is stated as: dense mode (default),
SessA-4 cluster rule, power 0.17. On similar-size Scroll 4 patches from `s4_good_patches.zip` it flagged 6 of 10 (T1
control, post hoc). Per COORD 15:05 item 2, with power ≈ 0.17 the checker half is reported as uninformative.

## F3: stacked patch pairs in index winding 28
- **Which windings:** index winding 28 (Y4: published w038, w039, w040 all map to our 28). No other index winding is
  flagged by Y4 as absorbing several published ones; 27 and 29 are reported as context with the same rule.
- **Stacked pair:** two different patches both with k = 28, having vertices with |Δθ| ≤ 2° and |Δz| ≤ 50 vox and radial
  separation 12–40 vox. θ, z, r about the index axis; vertices = every 4th grid node (16 vox spacing). A pair whose
  close vertices sit on opposite sides of the seam (θ within 2° of 0 on one side and 360 on the other) is excluded:
  same k across the seam is one turn apart by construction (results/seam).
- **Reported:** stacked pairs, patches involved, area (vertices of patch a with a stacked partner, 256 vox² each, in
  cm²; union over patches).
- **If stacked pairs exist:** the same-winding constraints joining them = SessA-12 solve edges directly between the two
  patches of a stacked pair. Each is scored with the checker's constraint rule (P1FIX, pre-registered):
  **failure = witness verdict `ambiguous` (agreement < 0.8) or `untestable` while its d_i term is used.** Failures are
  dropped, the index re-solved (same command), and turn counts (k span of the largest component; patches per k ≥ 27)
  reported before and after. The measured d_ii of each joining edge (round(radial sep ÷ 134 µm)) is also reported;
  a d_ii ≥ 1 on a same-winding edge is the measurement disagreeing with the index there. Y2 itself is SessD's script;
  SessA hands SessD the after index for the re-run.
- **If none:** the coordinator's wording applies.

## F2: page 1
- The 92 dropped constraints are listed with their witness verdict, agreement, n_testable and the criterion
  (already in `results/p1fix/page1_crossing.json` / `dropped_edges.json`, committed before this protocol).
- Checker on all patches matched by off-modal page-1 nodes under the after index (the 9.11 cm²): each patch's segment
  report (clusters, power, testable share). **No patch is dropped on a segment flag at power 0.17**, because the flag
  rate on known-good Scroll 4 control patches is 6 / 10. The result is reported as uninformative unless the page-1
  patches' clusters per cm² exceed the control's maximum on more than half of them (reported, not acted on). A drop
  on this basis needs a coordinator ruling. If no drop is made, the ruled wording applies: "index error, cause not
  found".
- Along-sheet unwrap as default: SessA's page agreement figures (`results/p1fix/rescore.json`) already use it. Minimum
  across the ten pages is quoted.

## F1: checker on 200 uniformly random placed patches
- Placed patches = the 56,934 patches of the SessA-15 whole-scroll index (the set quilt v2 places by the index). 200
  uniform draws, rng 20260930; same runner as T1 (sha-checked sources: the public zips), Scroll 4 CT, SessA-12 axis.
- **Predicted pass range at power 0.17: 25–60 %** (Scroll 4 control 4/10, Wilson 17–69 %).
- Reported: pass rate with Wilson 95 %, power per patch, and the statement that this does not measure single-sheet
  correctness.

## Predictions
- F3: stacked pairs in k = 28 exist (≥ 1): 80 %. Dropping failing joining constraints changes the k = 28 turn count
  (patches re-assigned out of 28) for < 10 % of its 509 patches: 70 %.
- F2: ≤ 50 % of page-1 minority patches exceed the control's maximum clusters per cm²: 60 %.
- F1: pass rate in 25–60 %: 60 %.

## Amendment (14:58Z, before any F2 checker run)
Page 1's off-modal area under the after index (9.11 cm²) lies on 940 patches (550 carry 90 % of it). At ~35 s per
segment run this does not fit before 19:00 London beside F1. The F2 checker therefore runs patches in order of their
off-modal area (largest first), results written as they finish; the report states the number of patches and the share
of the 9.11 cm² covered by the cutoff. The drop rule is unchanged (no drop on power-0.17 flags).
