# Audit blockers F1 (deck), F2 (page 5), F3 (outer windings): VP pre-registration (VP-M38, VP-M40)

Committed before any F-item number is computed, or any frame rendered. Everything is Scroll 4 (PHerc 1667), with
patches grown and released by Will Stevens (report12). The data is private, and it is all our own index (V1-15,
the tranche as in Y2, w_v as in Y2). Agent review is not adjudication. Thomas reads the deck.

## F1: blind deck through the whole-scroll trace (VP-M40 composition)
**Source of "trace cells".**
- SCALE's cell table for the whole-scroll quilt is not in git. The trace cells are therefore reconstructed here from
  the same inputs: indexed patches, the per-vertex winding w_v, and cells of 8 voxels.
- **Random trace cells (20):**
  1. Draw candidates uniformly over all valid indexed patch vertices (reservoir sample, seed 20260930).
  2. Accept each with probability 1/m, where m is the number of distinct indexed patches with a vertex in the same
     8-voxel 3-D cell.
  3. This makes the draw uniform over occupied cells, as the quilt counts each cell once.
  4. The first 20 accepted candidates with line coverage ≥ 0.6 across the frame (T1's filter) are used; rejections
     are counted.
- **Straddling a known index turn change (10):**
  1. Find pairs of indexed patches whose vertices lie within 4 vox of each other (same place, same surface as far as
     geometry shows), where the index gives them w_v differing by exactly 1 at the contact.
  2. Draw 10 contacts uniformly from all such pairs.
  3. Centre the frame on the contact, with the horizontal running from one patch into the other along the surface,
     and draw both patches' lines.
  - Our index claims that the line changes turn there. **A "one sheet" answer counts against the index** (LEAD's
    note).
- **Decoys (10):**
  - Each is a line transplanted from a random real frame (random-cell or straddling), at a position ≥ 60 vox from
    every indexed patch (8-voxel occupancy grid plus a distance transform), with CT above the real frames' 40th
    percentile.
  - The frame is oriented by the nearest patch normal, as T1's decoys were.
- **Frames:** 251 × 121 voxels (±125 along, ±60 across), trilinear from level 0 of 20231117161658, shown at 2 px per
  voxel with one pooled contrast window. The line is thin yellow; there are no labels; the order is shuffled so that
  decoys are not next to their donors. The key is sealed and its hash committed before Thomas reads.
- **Question (all 40): "Across the frame, is the yellow line on one sheet, or does it cross to another sheet?"**
  Answers: one sheet / two sheets / can't tell. Reading conditions are stated first; no going back; zoom at most 2×.
- **Reported:** "one sheet" rate per group (Wilson 95%).
  - For straddling frames, "two sheets" is the rate that supports the index.
  - For decoys, "one sheet" is the reader's rate of calling a line that follows no sheet a sheet (it should be ~0).
- **COORD's claim line:** "sampled single-sheet rate X% (reader, n=20)". n is 20 random cells, not 28, per the 15:05
  recomposition.
- **Predictions (VP, stated before reading):**
  - random cells, one sheet 17–20 of 20;
  - straddling, two sheets 6–10 of 10;
  - decoys, one sheet 0–1 of 10.
  - No pass/fail rule is attached to these; they are stated so the result can be compared with them.

## F2: does page 5's surface leave the papyrus at its boundary pieces?
- **Page:** Stevens' page 5 (patch_5). Pieces: D1 main-boundary pieces of page 5 (`stevens/followup/d1_main.json`),
  i.e. every piece with ≥ 50 points.
- **Band:** every page vertex within ±10 vox, in page-grid distance, of a piece.
- **Control:**
  - For each piece, the same polyline translated to 5 random positions on the same page.
  - Each translated band must lie entirely on valid vertices and ≥ 30 vox from any main-boundary piece.
  - The control fraction is pooled per piece.
- **On-papyrus vertex:**
  - The checker's rule, adapted: T = the page's own 5th percentile of vertex CT intensity (level 0, trilinear).
  - A vertex is on papyrus if the maximum CT along its normal, within ±3 vox at 1-vox steps, is ≥ T.
- **Rule (COORD, verbatim):** band fraction < 0.5 × control = "surface leaves the papyrus". This is scored per piece
  and pooled; the pooled result decides.
- **Otherwise:** build a page-5-only masked deck for Thomas.
  - 40 frames: frames at 25/50/75% along each piece, plus random along-piece positions, the deck-3 mask, the same H4
    rule, and a sealed key.
- **Secondary** (reported, not deciding): the same fractions with an absolute threshold T_abs, the 40th percentile of
  CT over a 50-vox cube around the page centre. T at the 5th percentile makes ~95% of vertices "on papyrus" by
  construction.
- **Prediction (VP):** not "leaves the papyrus". Band/control ratio 0.9–1.05. Page 5's boundary was judged a real
  switch in the blind decks, which means sheet to sheet, not sheet to air.

## F3: stacked pairs within one index winding
- **Data:** from the same tranche pass, per indexed patch and per bin (w_v, θ 2°, z 50 vox): vertex count, median r
  about V1-15's umbilicus, median xyz.
- **Stacked pair:** two different patches in the same (w_v, θ, z) bin whose median radii differ by 12–40 vox.
- **Reported:**
  - for every w_v, the stacked pair count and area (the smaller patch's vertices in the bin × 16 vox², ×(7.91 µm)²),
    listed first for w_v = 28 and for every winding Y4 flags (27–29 and 18);
  - the list of pairs for w_v = 28;
  - also, as a check, the count of such pairs at |Δw_v| = 1 (neighbouring windings, expected at the local pitch).
- **"Share of the 17.5 cm² inside published w036–w041":** SCALE's Q2 conflict cells are not in git. This part is
  reported as not computable here unless SCALE supplies the cells.
- **Prediction (VP):** stacked same-winding pairs exist at w_v = 28, in the outer turns where Y4 found three
  published windings on our 28. Area ≥ 1 cm².
- V1 does the constraint identification, re-solve and Y2 re-run (VP-M38 F3).
