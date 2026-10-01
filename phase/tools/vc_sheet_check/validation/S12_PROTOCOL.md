# S1, S2 (SessA instruction): Stevens' removals vs our flags, like for like — registered before computing

- **Population:** the 56,934 patches of SessA-15's Scroll 4 whole-scroll index. **His removals** = patches in
  `s4_bad_patches.zip` (9,171 released as bad); **his kept** = patches in `s4_good_patches.zip`. Label from the zip a
  patch id comes from (sha256 72f436c5… / 5c5a4865…).
- **Our joins:** SessA-12 solve edges (patch pairs). A join is **unsatisfied** if any of its terms (i, ii, iii) is in
  SessA-15's `unsatisfied.csv` (`results/v1-15/whole/`). **Flagged by us** = a patch with ≥ 1 unsatisfied join.
- **S1:** among patches flagged by us and kept by him, the share with ≥ 1 unsatisfied join to a patch he removed.
  Coordinator's prediction ≥ 60 %.
- **S2, primary (coordinator's text):** on the unsatisfied joins, repeatedly remove the patch that is in the most
  remaining unsatisfied joins (ties: smallest patch id) until none remain; the removed set is **our bad list**.
  2 × 2 against his removals over the population; Cohen's κ; both off-diagonal counts.
  - "Agreement on removed patches" = |ours ∩ his removals| / |his removals| (recall on his list, integrator's reading).
  - "Our-bad / his-kept" = |ours ∩ his kept| / |his kept|.
  - Coordinator's predictions: agreement ≥ 60 %; our-bad/his-kept ≤ 10 %.
- **S2, sensitivity (his exact tie rule):** `badpatchfinder.cpp` FindBadPatches lines 186–222 (WillStevens/scrollreading
  @ 62cbc21b) as reimplemented in `phase/writeup/w2_stats.py greedy()` (reproduced his 756 mode-b flags exactly, LEDGER
  SessN2-01): running frequency count over the pair list in order; pairs listed as (a, b) sorted. Reported beside the
  primary. Note: this is his attribution rule applied to **our** unsatisfied joins, not his pair scores.
- **SessA's predictions:** S1 ≥ 60 %: 50 % likely (flags mark joins, so adjacency is partly built in, but his removals
  are 16 % of patches). S2 agreement ≥ 60 %: 25 % likely (our unsatisfied joins are winding disagreements, his
  removals are pair-score failures; related, not the same). Our-bad/his-kept ≤ 10 %: 60 % likely.
