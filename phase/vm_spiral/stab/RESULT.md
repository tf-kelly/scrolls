# STAB result (prereg `phase/prereg/STAB.md`, sha256 2fd55d782ef2…, commit 527860c1)

- **Scorer and data:** `stab_score.py` (4188f2df) → `stab_result.json`. Harness `stab.py` (055a7578).
- **Runs:** local CPU, 23 solves of about 2–2.5 min each. £0, no VM.
- **Checks:**
  - **Identity control passed.** The unmodified solve through the harness changes 0 patches, with k exactly equal to SessA-15's.
  - **The F1b pool reproduces exactly:** 46,835 dw = 1 pairs, rebuilt with SessD's `pass1.py` unchanged.
- **Areas:** triangulated, from `stab_area.py` over tranche_s4_whole (2,028.8 cm² over 56,934 patches).

| Prediction (coordinator) | Outcome | Verdict |
|---|---|---|
| (a) < 5 % of kept area changes winding after removing Stevens' bad patches | **7.1 %** (119.6 of 1,683.3 cm²; 3,897 of 47,764 patches) | **MISS** |
| (b) ≥ 4 of F1b's 7 "same" contacts in the pool's bottom stability quartile | **1 of 7** | **MISS** |

## Numbers
- **(a), Stevens-bad removed (9,170 indexed patches; 117,295 of 174,641 joins remain):**
  - The re-solve has 304 components.
  - 11.2 cm² of kept area lies outside the new largest component.
- **Null, 9,170 random patches removed (seed 20260931), same harness:**
  - **6.2 %** changed (105.9 of 1,701.2 cm²; 3,133 patches); 173 components.
  - So removing Stevens' bad patches moves about 0.9 points more area than removing the same number at random.
- **(b), the pool (46,835 pairs):**
  - Mean pair stability 0.974. 13.9 % of pairs are below 1; the quantiles are 5 % 0.80, 10 % 0.95 and 25 % 1.0.
  - Because 86 % of pairs are perfectly stable, the registered mid-rank rule makes "bottom quartile" equal to "stability < 1" (mid-rank percentile ≤ 0.139). This is stated here, not changed.
  - **F1b's 7 "same" contacts:**
    - six have stability 1.0;
    - one, 530fbb16 (patches 134979/138270, w 15/14), has 0.70;
    - so 1 of 7 are in the bottom quartile. Random placement would give 1.75.
  - **F1b's 12 "different" contacts:** 4 of 12 are in the bottom quartile (stabilities 0.40, 0.70, 0.75, 0.95).
  - No pair from either group split across components in any re-solve.
- **(b)(ii), per-patch stability, reporting only:**
  - Index windings 26–30 (2,554 patches): 43.0 % have stability < 1.
  - All other patches: 12.9 %. Overall: 14.3 %. Median 1.0 in both.

Numbers only; no interpretation before the coordinator rules. Stability is not correctness.

## Page 1 (coordinator request 21:20, SessB instruction). EXPLORATORY: not in the STAB prereg
- **Source:** the same 20 jackknife re-solves (SessA-15 edges and index), scored by `page1_jk.py` → `page1_jk.json`.
- **Page-1 sets:**
  - <branch> `p1fix/page1_crossing.json`: sides M and m, split nodes, and 633 crossing joins;
  - `f2/f2_runs.jsonl`: the 940 minority patches.
  - SessA built these sets on index e077f6da (after P1FIX). The jackknife here is on SessA-15's index.

| set | n | share with stability < 1 | mean stability | share ≤ 0.5 |
|---|---:|---:|---:|---:|
| all patches (scroll) | 56,934 | 14.3 % | 0.970 | 1.6 % |
| page-1 minority patches (F2's 940) | 940 | **55.7 %** | 0.878 | 13.4 % |
| side M (majority) | 368 | 34.0 % | 0.973 | 0.3 % |
| side m (minority) | 125 | **68.8 %** | 0.851 | 16.0 % |
| split nodes | 177 | 58.2 % | 0.903 | 6.2 % |

- **Joins crossing the page-1 boundary (633):**
  - 35.9 % have pair stability < 1 (mean 0.929).
  - Of the 169 joins with unsatisfied terms, **63.3 %** are unstable, against 25.9 % of the satisfied ones.
  - A join counts as split when its two patches fall in different components of a re-solve: 7 join-runs in total.
- **Numbers only.** A patch is unstable when dropping 10 % of joins moves its winding. That is not evidence of which winding is correct.
