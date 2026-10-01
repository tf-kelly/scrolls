# S3: which method is right on the disagreements? Blind deck, 10 frames per cell of V1's S2 table (V1-M48 / VP-M43)

Committed before any patch is drawn or any frame rendered.

**Cells:** the 2×2 of V1's S2 table (d6bf993e, `results/s12/`), reproduced exactly here.
- "Ours bad" is V1's greedy-attributed bad list, 7,139 patches (`s12_result.json`, `our_bad_list`).
- "His removed" is every patch in Will Stevens' `s4_bad_patches.zip` (report12; public at
  dl.ash2txt.org/community-uploads/will/). Its ids were read from the zip's own file directory:
  `his_removed_ids.json`, 9,171 ids, of which 9,170 are indexed.
- Population: V1-15's 56,934 indexed patches.

| cell | definition | patches |
|---|---|---|
| BB | ours bad, his removed | 3,159 |
| HO | his removed only | 6,011 |
| OO | ours bad only | 3,980 |
| GG | both good | 43,784 |

**Draw:** 10 patches per cell, uniform within the cell (seed 20260933).
- Patches with fewer than 50 valid vertices are skipped.
- A draw is rejected if the patch's line crosses less than 60% of the frame (T1's filter). Rejections are counted
  per cell.

**Frame:** T1's design on Scroll 4.
- The section passes through the patch's most central valid vertex.
- Vertical is the patch normal there. Horizontal is a random direction in the tangent plane.
- 251 × 121 vox, trilinear from level 0 of 20231117161658, 2 px per voxel, one pooled contrast window.
- The patch's own line is drawn thin yellow, computed numerically. There are no labels, and the order is shuffled.
- The key is sealed and its hash committed before Thomas reads.

**Question (COORD):** "Does the yellow line stay on one sheet across the frame?" Answers: yes / no / can't tell.
Conditions are stated first; no going back; zoom at most 2×.

**Reported:**
- "yes" rate per cell (Wilson 95%). No pass/fail (COORD).
- On the disagreements, the method whose flags show the lower "yes" rate is the one the reader's judgement favours:
  - HO low and OO high: his removals are the real errors;
  - OO low and HO high: ours are;
  - both high: neither method's disagreement patches show errors at patch centres.
- With n = 10 per cell, only large differences are visible.

**Predictions (VP, stated now):**
- GG 9–10/10 yes; BB 5–9; HO 6–10; OO 6–10.
- Most likely outcome: no cell below 5/10, because frames at patch centres miss errors near edges and joins. T1
  (28/28) and F1 (20/20) found centres clean.
- So the deck will probably not separate the methods. That limit is stated in advance.

**Limits, stated in advance:** patch centres only; one reader; 10 per cell.
