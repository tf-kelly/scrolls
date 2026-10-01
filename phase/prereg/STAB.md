# STAB: Scroll 4 index re-solve stability (coordinator ruling 19:50, item 2; SessB instruction; owner SessB)

Committed before any (a) or (b) re-solve is run. At the time of commit SessB has only these results: the unmodified full
solve reproduced, and the 2×2 of `s4prov/RESULT_2x2.md`.

## 1. Question
- **(a)** When Stevens' 9,171 "bad" patches are removed and the Scroll 4 index is re-solved, does the winding of less
  than 5 % of the kept patches' area change (after aligning free offsets)?
- **(b)** In a 20-fold 10 %-join jackknife, do at least 4 of F1b's 7 reader-unsupported turn-change contacts fall in the
  bottom stability quartile of F1b's candidate pool?

## 2. Design
- **Solver:** `vc_sheet_check solve --edges solve_edges.json --spacing-um 134`, with SessA-15's tie-break default.
  - Code is <branch> `61eb8e2b` (`phase/tools`), run locally. ortools 9.15.6755 is installed here, because the container
    lacked it.
- **Edges:** SessA-12 `solve_edges.json` (sha256 6e6eb5f1…): 174,641 joins over 56,934 nodes.
- **Axis:** `axis_contract_allpatches_zyx.txt` (8260079a…).
- **Baseline check, done before this file:** the unmodified solve reproduces SessA-15 `whole/wrap_index.csv` byte for byte
  (sha256 1c0b7d30…). It took 148.7 s CPU, so N = 20 as ruled.
- **Harness:** `phase/vm_spiral/stab/stab.py`. It is committed with or after this file, before any re-solve.
  - It changes only the edge list and node list passed to the same `build_state`/`solve` calls as the CLI.
  - `thN` (the centroid angle) is per patch and does not depend on which edges are present.
- **(a)** Remove every node in `s4_bad_patches.zip` (9,170 are indexed) and every join touching one; re-solve.
  - **Kept patches:** the 47,764 indexed good patches.
  - **Alignment:** per **new** component c′, offset o(c′) = the mode over its patches of (k_new − k_full). This is the
    best offset per new component, against the full solution.
  - A kept patch **changed** iff k_new − o(c′) ≠ k_full.
- **(b)** 20 re-solves, i = 0..19. Each drops 17,464 joins (10 % of 174,641, rounded down), drawn uniformly without
  replacement with `numpy.random.default_rng(20260930 + i)`.
  - A join is an edge, not an LP term: all of an edge's terms go together.
  - All nodes are kept.
  - **Pair stability** of a contact (a, b) = the fraction of the 20 re-solves in which a and b are in the same
    re-solve component AND k_a − k_b equals the full solution's k_a − k_b.
    - This needs no alignment, because the component offset cancels.
    - Different components count as not agreeing, and that count is reported.
  - **Patch stability** = the fraction of re-solves in which k − o(c′) = k_full, with the same per-component mode
    alignment as (a).
- **Patch area:** the triangulated surface area of each patch's tifxyz grid, in voxel² then cm² (7.91 µm).
  - Each valid 2×2 quad counts as 0.5·|d₁ × d₂|, where d₁ and d₂ are its diagonals.
  - Computed by `stab_area.py` from tranche_s4_whole `dataset.tgz` (81926ab5…).
  - The committed `stevens_areas.json` covers only 5,153 patches, so it is not used.
- **F1b candidate pool:** rebuilt by running SessD's `pass1.py` unchanged (<branch>), followed by `build_f1b.py`'s pair loop
  (lines 36–47, unchanged): dw = 1 contact pairs, excluding F1's straddle pairs.
  - **Input check:** the pool must reproduce "candidate pairs dw=1 46,835". If it does not, (b) is reported UNTESTED.
- **The 7 contacts:** F1b TC items answered "same" (`score_f1b.json`, <branch>):
  - 15766/23460;
  - 160411/161458;
  - 129381/136949;
  - 29107/37416;
  - 76460/106932;
  - 35443/41666;
  - 134979/138270.

## 3. Controls
- **Positive/identity control:** the unmodified full solve through the same harness must return every patch unchanged
  (changed area 0, pair stability 1 for every pool pair). Run first, reported.
- **Null for (a):** drop a random 9,170 indexed patches, matched in count, with `default_rng(20260931)`, through the
  same harness. Report its changed-area share beside (a).
  - This separates "removing bad patches" from "removing a sixth of the graph".
- **Null for (b):** the expected count of the 7 in the bottom quartile under random placement is 7 × 0.25 = 1.75.
  - Also reported: the same count for F1b's 12 "different" TC contacts, through the same harness.

## 4. Predictions (the coordinator's, ruling 19:50)
- **(a):** changed share of kept area < 5 %.
- **(b):** at least 4 of the 7 are in the bottom stability quartile.
- SessB makes no prediction of its own.

## 5. Metric and scorer
- **(a):** changed kept area ÷ kept area. Also reported:
  - the changed patch count;
  - the area in new components that are not the new largest component;
  - the same numbers for the null.
- **(b), bottom quartile:** pool pairs are ranked by pair stability, ascending, with ties given their mid-rank. A pair is
  in the bottom quartile iff its mid-rank percentile, (mid-rank − 0.5) / n, is ≤ 0.25.
  - Count the 7 that meet this; if a contact is not in the pool, report that and count it as not bottom.
  - Also reported:
    - the pool's stability distribution;
    - each of the 7's stability;
    - the 12 "different" contacts' count.
- **(b)(ii), reporting only:** patch stability for patches with full k ∈ [26, 30] (the w038–w040 zone) against all
  others: the median and the share < 1.

## 6. Held-out set
Nothing is tuned. The 7 and the 12 were fixed by F1b (<branch> 25537407) before this file.

## 7. Acceptance
- (a) HIT iff share < 0.05.
- (b) HIT iff count ≥ 4 of 7.
- Otherwise MISS.
- UNTESTED if:
  - the identity control fails;
  - the pool does not reproduce 46,835;
  - results are not produced by 23:30 London, in which case they are "not completed".

## 8. Budget
- Local container CPU only, £0, 0 GPU-h, no VM.
- Kill criterion: stop at 23:30 London.

## 9. Data and licence
- Scroll 4 (PHerc 1667) and W. Stevens' public patch zips (dl.ash2txt.org/community-uploads/will/).
- Tranche data stays in the private bucket and scratch. Only numbers are committed.
- Stability is not correctness: a systematic index error can be perfectly stable.
