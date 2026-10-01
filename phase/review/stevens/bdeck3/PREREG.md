# Blind deck 3: masked middle (COORD 04:25)

This file and `score_bdeck3.py` are committed, with this file's sha256 in the commit message, **before**
`build_bdeck3.py` draws or renders anything. The sealed key's sha256 is committed with the deck. Responses are
committed unchanged before the key is opened. Deck 3 adds to decks 1 and 2 and replaces neither.

## Why
In decks 1 and 2 the reader could have judged the shape of the yellow line (a kink where the mesh deforms) rather
than which sheet it is on. Deck 3 hides the line where a kink would be and asks only whether the two visible ends
are on the same sheet.

## Frames
- **Same crop, contrast and scale as deck 2:** a CT section at level 0, ±150 vox (in-page) × ±60 vox (page normal),
  1 px/voxel shown ×2. The contrast is deck 1's window, u16 [12987.91, 42732.73].
- **His line** is drawn thin in yellow (`section_geometry.surface_segments`) **only where |x| ≥ 50 vox from the frame
  centre.** Each segment is clipped at x = ±50 vox, so the line stops cleanly there.
- **The middle band, |x| < 50 vox, shows CT only:** no line, no mask, no edge marker.
- No ticks, no labels, random 8-hex ids, shuffled once.

## Question and answers
- Question: **"Are the left and right yellow segments on the same sheet?"**
- Answers: **same sheet / different sheet / can't tell**, plus an optional note.
- One frame at a time, no going back, zoom 2× at most.
- Reading conditions are stated by the reader first.

## Composition (counts drawn with `secrets` within ranges, sealed, not disclosed)
| group | source | count |
|---|---|---|
| R02 real, pages 0 + 2 | page 0 piece 1 (arc ≥ 90 cells), page 2 pieces 1–2 | 10–14 |
| R5 real, page 5 | page 5 pieces 1–2 | 6–8 |
| P1R page 1 remainder | page 1 smoothed-q' boundary pieces, as deck 2's UNK (same residual-edge exclusion proxy) | 5–7 |
| ART artefact | page 0 piece 2, page 1 pieces 1–2 | 6–8 |
| DEC decoys | centre ≥ 100 vox from any q or q' boundary; pages 0, 2, 3, 4, 5, 6, 7, 8, 9 | 8–10 |

- **Decoy split:** half the decoys (rounded down) are **deformed-mesh decoys (DD)**: at least 20% of valid grid cells
  within 2.5 cells of the centre carry P3's "any" flag (normal flip, near-self-contact or cell-area ratio outside
  [0.5, 2]; P3 definitions, 81e18d6). The rest are **plain decoys (DP)**: under 5% of those cells flagged.
- Within a group, frames are split over pieces or pages in proportion to piece length, or page valid area for
  decoys, by largest remainder. Pages where no candidate qualifies get none.
- **Placement:**
  - frames on one piece, or decoys on one page, are ≥ 60 vox apart;
  - **no frame centre within 30 vox (3D) of any deck-1 or deck-2 frame centre;**
  - ≥ 90% valid page along the ±150-vox line.

## Hypothesis and rule
A rate is (frames answered X) / (frames in the group). Can't-tell counts as neither.
- **H4:** "different sheet" rate on R02 ≥ 2/3 **AND** "different sheet" rate on ART + DP ≤ 1/4.
- **H5 (descriptive, P1R):** "same sheet" rate reported; no rule.
- **Descriptive, no rule:**
  - DD's "different sheet" rate, reported separately. A high DD rate would mean the reader answers from mesh shape
    even with the middle hidden, or that the mesh does switch there unflagged by our index. The deck cannot tell
    which.
  - R5's rates.
- **Also reported:** per group, all three answer counts with Wilson 95% intervals; can't-tell rate per group; the
  median answer time per frame; d′ for H4 (R02 against ART + DP, log-linear corrected).
- **Consequence, as COORD set it:**
  - If H4 holds, the shape-cue limit is removed from CLAIMS.
  - If H4 fails, or can't-tell > 1/2 on R02, the switch claim is stated with the limit: "blind readers separate
    flagged boundaries from controls; whether they judge sheet continuity or mesh shape is not established."

## Reader limits (recorded in advance)
One reader, not naive to the pages. He knows the composition and results of decks 1 and 2. Agent review is not human
adjudication. The frames are machine-generated sections of a machine-generated mesh. With the middle hidden, "same
sheet" requires tracing sheets through the unmarked band. Where sheets are tight that may be hard, and a high
can't-tell rate is a possible outcome.
