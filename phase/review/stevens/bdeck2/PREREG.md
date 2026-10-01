# Blind deck 2: replication, pre-registered per page (COORD 03:54)

This file and `score_bdeck2.py` are committed, with this file's sha256 in the commit message, **before**
`build_bdeck2.py` draws or renders anything. The sealed key's sha256 is committed with the deck, before Thomas opens
it. His responses are committed unchanged before the key.

## Groups and counts
Counts are drawn at random within the ranges below (Python `secrets`). The draw is repeated until the total is in
56–64, then sealed in the key and not disclosed to the reader.

| group | source | count |
|---|---|---|
| R02 real, pages 0 + 2 | page 0 piece 1, page 2 pieces 1–2 (D1 main-boundary polylines, the D4' pieces) | 14–18 |
| R5 real, page 5 | page 5 pieces 1–2 | 8–12 |
| ART artefact | page 0 piece 2, page 1 pieces 1–2 (quilt2 unwrap branch cuts, SEAM.md) | 6–10 |
| DA decoy | pages 0, 2, 5; centre ≥ 100 vox from any boundary | 8–10 |
| DB decoy | pages 3, 4, 6, 7, 8, 9; centre ≥ 100 vox from any boundary | 8–10 |
| UNK unknown | page 1, the boundary that remains under the sheet-unwrapped key q' (the 13.4 cm²) | 6 |

- **Within a group:** frames are split over its pieces or pages in proportion to piece length, or to page valid area
  for decoys, by largest remainder.
- **"Any boundary" for decoys:** the D1 smoothed boundary under q and under q' (`seam_unwrap.py`), as in deck 1.
- **Unknown pieces:** connected boundary pieces of page 1's smoothed q' map with ≥ 50 edge points. Excluded: points
  within 25 cells (100 vox) of the 3368 grid edges where even the along-sheet unwrap jumps by more than π. Those are
  unwrap residuals, not boundaries.

## Placement (seeded; build_bdeck2.py)
- Boundary frames are centred on the piece and oriented perpendicular to it. Decoys point in a random in-page
  direction.
- Frames on one piece, or decoys on one page, are ≥ 60 vox apart.
- **No frame centre is within 30 vox (3D) of any deck-1 frame centre.**
- Page 0 piece 1 frames lie beyond arc 90 cells, as in deck 1 (Thomas has seen that piece's first flipbook
  frames).
- Every frame has ≥ 90% valid page along its ±150-vox line.

## Frames
- **Same crop, contrast and scale as deck 1:** a CT section at level 0, ±150 vox (in-page) × ±60 vox (page normal),
  1 px/voxel shown ×2. His surface is drawn thin in yellow by `section_geometry.surface_segments`.
- **Contrast:** deck 1's window, u16 [12987.91, 42732.73], reused unchanged, so both decks share one contrast.
- No ticks, no labels, random 8-hex ids, shuffled once.

## Question and answers
- Question: **"Follow the yellow line from left edge to right edge."**
- Answers: **switches sheet / stays on one sheet / leaves the papyrus / can't tell**, plus an optional note.
- One frame at a time, no going back, zoom 2× at most.
- Reading conditions are stated by the reader first.

## Hypotheses and rules
A rate is (frames answered "switches sheet") / (frames in the group). "Leaves the papyrus" and "can't tell" count as
not-switch.
- **H1, replication:** switch rate on R02 ≥ 2/3 **AND** switch rate on ART + DA + DB ≤ 1/4.
- **H2, page 5** (from deck-1 notes): on R5, switch rate ≤ 1/3 **AND** "leaves the papyrus" rate ≥ 1/2.
- **H3, artefact control:** switch rate on ART ≤ 1/4.
- **UNK:** descriptive only, no rule.

## Reporting
- Per group: all four answer counts, with rates and Wilson 95% intervals.
- d′ for H1: R02 against ART + DA + DB, log-linear corrected.
- DA and DB false alarms are also reported separately.
- **Deck 1 and deck 2 are both reported, whatever the outcomes. Neither replaces the other.**

## Reader limits (recorded in advance)
One reader. He is not naive to these pages: he has seen the D4' flipbooks non-blind, and he knows deck 1's
composition and its unblinded results, including the page 5 notes that motivate H2. Agent review is not human
adjudication. The frames are machine-generated sections of a machine-generated mesh.
