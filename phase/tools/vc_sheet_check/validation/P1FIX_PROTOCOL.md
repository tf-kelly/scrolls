# Page-1 index error: correct via the checker, not by hand (COORD → SessA 04:31 London)

Committed before any page-1 geometry is read.

## Inputs
- Index: SessA-15 whole-scroll Scroll 4 index (`results/v1-15/whole/wrap_index.csv`, sha256 1c0b7d30…, s = +1, axis
  `results/v1-12/run/axis_contract_allpatches_zyx.txt`), solved from SessA-12's `solve_edges.json` (bucket v112/results,
  sha256 6e6eb5f1…, checked) with `vc-sheet-check solve --spacing-um 134` (tie-break default). Pair table
  `v112/results/pairs.csv` (witness n_testable, agreement, verdict).
- Pages: W. Stevens' `s4_10_components_tifxyz.zip` (public, sha256 8af35fb6… as SessD pinned), page k = `patch_k`.
- Patches: `s4_good_patches.zip` / `s4_bad_patches.zip` (sha256 5c5a4865… / 72f436c5…).
- SessD's page-1 result (<branch> `phase/review/stevens/followup/SEAM.md`): 13.40 cm² off the modal key under q'
  (θ unwrapped along the sheet); deck 2: 0/6 switch there.

## Step 1: page key and boundary (SessA's own implementation; SessD's is not rerun)
- Page vertices, every 4th grid node. Each is assigned to the nearest vertex of an indexed patch within 4 vox (patches
  with a bbox within 64 vox of the page's). Its key = round(k_patch + s·(thN_patch − Θ′)/2π), Θ′ the page's angle
  about the axis unwrapped along the page grid (BFS spanning tree over valid 4-neighbours). Only the largest connected
  island is used (other islands have no along-sheet link; their area is reported as excluded). Seam-free by
  construction; residual unwrap jumps (non-tree edges with |ΔΘ′| > π) are counted.
- Boundary = page grid edges joining two different keys, after SessD's 15×15 majority smoothing. Minority area reported
  next to SessD's 13.40 cm²; a large difference is reported, not reconciled by tuning.
- Sides: indexed patches matched by modal-key vertices (side M) and by minority-key vertices (side m), each within
  50 vox of the boundary. A patch matched on both sides is listed separately (it is itself split by the boundary).

## Step 2: crossing constraints and the checker
- Crossing constraints: SessA-12 solve edges with one patch on side M and the other on side m (plus edges touching a
  both-sides patch). For each: d_i, d_ii, Stevens, witness n_testable / agreement / verdict, and whether any of its
  terms is unsatisfied in SessA-15.
- **Constraint below threshold:** witness verdict `ambiguous` (agreement < 0.8, the verdict rule) or `untestable`
  (n_testable = 0) while its d_i term is used; these are the only thresholds the solve's measurements have.
- **Patch failing the sheet check:** `vc_sheet_check segment` on the patch (Scroll 4 CT, the SessA-12 axis, defaults)
  reports ≥ 1 layer-jump cluster at power ≥ 0.5. A run with power < 0.5 is "not a clean-segment test": inconclusive,
  not a fault.

## Step 3 / 4 (as ruled)
- ≥ 1 fault: drop it (a failing patch: all its edges; a constraint below threshold: that edge), re-solve with the
  same command, commit before/after solves with hashes, and report per page (all ten) the change in agreement
  (share of matched vertices on the modal key, same assignment as step 1) and the total constraint count changed.
- No fault: no change; record "index disagrees with page 1 over 13.4 cm²; no faulty input identified; left as an open
  error".
- No edit on the basis of the page alone. Pages 0 / 2 / 5 are not treated.

## Predictions (SessA, before data)
- P1: SessA's page-1 minority area is within ±30 % of SessD's 13.40 cm² (60 %).
- P2: at least one crossing constraint is below threshold (70 %): the core page is where witnesses are sparsest.
- P3: at least one side patch fails the segment check at power ≥ 0.5 (40 %).
- P4: if faults are dropped, page 1's modal share rises by < 10 points (60 %): one bad input rarely explains 13 cm².
