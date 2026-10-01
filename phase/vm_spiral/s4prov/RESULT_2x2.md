# Stevens bad/good × our contradiction flags: result (prereg d734b78d)

- **Flag file:** the default, SessA-15 `whole/unsatisfied.csv` (6694e964…). It has 23,857 rows and 17,109 flagged patches,
  which is the same count SessJ's quilt reports. SessA has not yet named a file (item 2). Scorer: `table2x2.py`. Output:
  `table2x2_default.json`.

|                  | flagged | unflagged | n      | flagged share |
|------------------|--------:|----------:|-------:|--------------:|
| Stevens bad      | 5,521   | 3,649     | 9,170  | **60.2 %**    |
| Stevens good     | 11,588  | 36,176    | 47,764 | **24.3 %**    |
| not in the index | –       | –         | 34 (33 good, 1 bad) | – |

- **Prediction (bad ≥ 40 % AND good < 10 %): does not hold.**
  - The bad arm passes (60.2 %).
  - The good arm fails (24.3 %, well above 10 %).
- **Association:** strong in the direction predicted. The odds ratio is 4.7: the odds of a flag are 1.51 for bad
  patches and 0.32 for good ones. Of all flagged patches, 32 % are Stevens-bad, against a 16 % base rate.
- **By join count (SessA-12 edges per patch), reporting only.** The flagged share, bad vs good, in each quartile:
  - Q1: 46 % vs 17 %;
  - Q2: 57 % vs 22 %;
  - Q3: 59 % vs 25 %;
  - Q4: 65 % vs 31 %.
  - Median joins: bad 7, good 6.
  - The flag rate rises with join count in both classes, but the gap holds within every quartile. So the enrichment is
    not just a join-count effect.
- **Reading:**
  - Our flags pick up most of what Stevens called bad (60 %).
  - They also flag about a quarter of his good patches, so they are not a filter that matches his.
  - Two readings fit the data, and this table cannot tell them apart:
    - a flag marks a *join* that fails, so a good patch next to a bad one gets flagged too;
    - his good set contains patches our index finds contradictory.
  - Neither label set is ground truth.

## The 34 patches not in the index
- **Ids:** listed in `not_in_index_34.txt`: 33 from `s4_good_patches.zip` and 1 from `s4_bad_patches.zip`.
- **Why they are missing:**
  - 33 of them appear in SessA-12 `pairs.csv` (v112/results) only in pairs whose verdict is `coincident` (102 rows).
  - One, patch 162082 (good), appears in no pair at all.
- **What that does:** a coincident pair produces no solve edge. SessA-12 `solve_edges.json` has 174,641 edges over exactly
  56,934 nodes, and none of the 34 is among them. SessA-15's index is solved from those edges, so the 34 have no winding
  and are absent.
- They were not filtered for quality. They lie on top of another patch and join nothing else.

## Area figures (quilt_membership.py, `quilt_membership_result.json`)
- **Setup:** SessJ's `quilt.py` was imported unchanged on tranche_s4_whole (81926ab5…, verified), with the default flag
  file.
  - It reproduces the ARC build's totals **exactly**: trace 648.325, conflict 17.506, all-patch conflict 32.595 cm².
  - Local CPU, 822 s, $0.
  - Areas are projected ((θ, z) cells of 4 vox).
  - 3,649 Stevens-bad patches are unflagged and so remain in the quilt, 9.2 % of the 39,825 unflagged indexed patches.

| quilt area | total cm² | from/inside Stevens bad | share |
|---|---:|---:|---:|
| Trace, ≥ 1 bad contributor | 648.3 | 123.5 | **19.1 %** |
| Trace, all contributors bad | 648.3 | 35.5 | 5.5 % |
| Conflict (flagged dropped), bad patch in the cell's extreme pair | 17.5 | 3.5 | **20.1 %** |
| Conflict (flagged dropped), any bad contributor | 17.5 | 5.8 | 33.3 % |
| Conflict (all patches), bad patch in the extreme pair | 32.6 | 12.4 | **37.9 %** |
| Conflict (all patches), any bad contributor | 32.6 | 18.8 | 57.6 % |

- **Conflict rate per covered cell (flagged dropped):**
  - cells with a bad contributor: 5.82 / (123.5 + 5.82) = 4.5 %;
  - cells without one: 11.68 / (524.8 + 11.68) = 2.2 %.
  - Cells a bad patch reaches conflict about twice as often.
- **Reading:**
  - Dropping flagged patches already removes most of the bad patches' conflict (18.8 → 5.8 cm² with a bad contributor).
  - The 3,649 bad patches our flags miss still touch a fifth of the trace area. Only 5.5 % of the trace area rests on
    bad patches alone.
  - "Our 648.3 cm²" should therefore be described as including a share of his rejected patches. A quilt without them
    would be smaller, but not by 19 %: most of those cells also have a good contributor.
