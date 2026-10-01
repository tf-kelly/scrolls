# P3 fold check: results (supporting only)

- Pre-registration 81e18d6. Script `p3_fold.py`, output `p3_fold.json`.
- Input: his tifxyz only.
- Rates: flagged cells / valid cells. "any" = normal flip (a) or near-self-contact (b) or cell-area ratio outside
  [0.5, 2] (c).
- Control: both 100-vox-shifted bands pooled; control cells near any D1 boundary are dropped.

| page · piece | kind | band any | control any | ratio | (a) band/ctrl | (b) band/ctrl | (c) band/ctrl | elevated | prediction | correct |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 · 1 | real | 28.4% | 16.2% | 1.75 | 9.5 / 5.6% | 2.9 / 0.8% | 22.7 / 12.7% | no | elevated | **no** |
| 0 · 2 | artefact | 1.5% | 3.1% | 0.47 | 0 / 2.5% | 0 / 0.6% | 1.5 / 1.4% | no | not | yes |
| 1 · 1 | artefact | 1.2% | 0.7% | 1.70 | 0.05 / 0.07% | 0 / 0.02% | 1.2 / 0.7% | no | not | yes |
| 1 · 2 | artefact | 0.0% | 0.0% | — | 0 / 0 | 0 / 0 | 0 / 0 | no | not | yes |
| 2 · 1 | real | 10.8% | 7.1% | 1.53 | 4.6 / 2.5% | 0.07 / 1.2% | 7.6 / 4.9% | no | elevated | **no** |
| 2 · 2 | real | 11.5% | 4.0% | 2.85 | 3.7 / 2.0% | 0 / 0 | 9.4 / 2.4% | **yes** | elevated | yes |
| 5 · 1 | real | 5.7% | 4.8% | 1.19 | 2.2 / 2.4% | 0 / 0.03% | 4.3 / 3.0% | no | none | — |
| 5 · 2 | real | 3.3% | 0.9% | 3.58 | 0.2 / 0.6% | 0 / 0.06% | 3.2 / 0.3% | **yes** | none | — |

## Ruling against the pre-registered rule
- **Elevated:** page 2 piece 2, page 5 piece 2.
- **Not elevated:** the other six.
- **Coordinator's prediction:** 4 of 6 correct. All three artefact pieces were correctly not elevated. Page 2
  piece 2 was correctly elevated. Page 0 piece 1 and page 2 piece 1 were predicted elevated but fall below the 2×
  ratio: 1.75× and 1.53×.

## Descriptive (not part of the ruling)
- Every real-boundary piece has a higher "any" rate in its band than in its controls: 1.19× to 3.58×. The artefact
  pieces do not: 0.47×, and 1.70× at under 1% absolute, and 0/0. The sign pattern follows real versus artefact
  across all 8 pieces. The 2× threshold separates only two of the five real pieces.
- Page 0 piece 1 has by far the highest absolute fold rates: 28% of band cells flagged, against 16% in its
  controls. The whole neighbourhood of that boundary is heavily deformed mesh, so the ratio stays below 2.
- Most of the excess is cell-area distortion (c). Normal flips (a) are raised at page 0 piece 1 and page 2 pieces
  1–2. Self-contact (b) is raised only at page 0 piece 1 (2.9% against 0.8%).
- Page 5 piece 2's elevation is almost entirely area ratio: 3.2% against 0.3%, with no flips. That fits a stretched
  mesh rather than a fold. It is consistent with the deck-1 page 5 hypothesis ("his mesh leaves the sheet"), but
  does not test it.

## Limits
- Cells are spatially correlated, so the p-values overstate independence. The ratio and absolute conditions carry
  the ruling.
- Control bands dropped 71–2425 cells near other boundaries (page 5 piece 1: 2425).
- The mesh is machine-generated. A fold statistic describes the mesh, not the papyrus. Supporting only.

## Post hoc extension (COORD 04:25 item 2): page 1 remainder
This was not in the 81e18d6 pre-registration. `p3_p1r.py` → `p3_p1r.json` applies the same measures and bands along
page 1's remaining boundary under the sheet-unwrapped key q'. These are the pieces decks 2 and 3 sample: 112 pieces,
pooled as one band, with 716 residual edges excluded.

| group | band any | control any | ratio | (a) band/ctrl | (b) band/ctrl | (c) band/ctrl | elevated by P3 rule |
|---|---|---|---|---|---|---|---|
| page 1 remainder | 2.6% (1795/69357) | 1.8% (3198/180594) | 1.46 | 0.81 / 0.65% | 0.81 / 0.61% | 1.61 / 0.98% | no |

## COORD 04:25 item 2: prediction scored per piece, hit or miss
| piece | predicted | observed (rule) | score |
|---|---|---|---|
| page 0 piece 1 | elevated | not elevated (1.75×) | **miss** |
| page 2 piece 1 | elevated | not elevated (1.53×) | **miss** |
| page 2 piece 2 | elevated | elevated (2.85×) | hit |
| page 0 piece 2 (artefact) | not | not (0.47×) | hit |
| page 1 piece 1 (artefact) | not | not (1.70×, under 1% absolute) | hit |
| page 1 piece 2 (artefact) | not | not (0/0) | hit |

The result is 4 hits and 2 misses. Page 5 had no prediction; piece 2 is elevated and piece 1 is not. The page 1
remainder had no prediction; it is not elevated (1.46×).

**On the proposed wording** ("his mesh is locally deformed along every index-flagged boundary (P3), located
independently of our index"). VP flags two problems:
1. **"Every" holds only as a direction.** All 5 real pieces and the page 1 remainder have band rates above control,
   at 1.19–3.58×. Only 2 of the 5 real pieces meet the pre-registered "elevated" rule.
2. **"Located independently of our index" holds for the flags, not the bands.** The fold flags are computed from his
   mesh alone. The bands are placed by our index's boundaries.

Suggested wording: "Fold/stretch flags computed from his mesh alone are more frequent along each of our index's
real disagreement boundaries than in nearby controls (1.2–3.6×; 2 of 5 pieces meet the pre-registered 2× rule), and
not along the index-only artefact boundaries."
