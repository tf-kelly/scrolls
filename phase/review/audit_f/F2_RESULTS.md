# F2: page 5, does the surface leave the papyrus at its boundary pieces? (PREREG_F.md, 244c518e)

Script `f2_page5.py` → `f2_page5.json`. It covers Stevens' page 5 and all 21 D1 main-boundary pieces.
- Bands: ±10 vox, 18,354 band vertices in total.
- Controls: 5 translated copies per piece, 88,091 vertices.
- CT: level 0, nearest voxel, maximum along the normal over ±3 vox.
- T: the page's own 5th percentile, 15,309 (u16).

| | band | control | ratio |
|---|---|---|---|
| **registered (T = page p5)** | **0.999** | **1.000** | **0.999** |
| secondary (T_abs = p40 of a 101-vox cube, 19,979) | 0.940 | 0.994 | 0.945 |

- **Ruling: "surface leaves the papyrus" is NOT met.** The pooled ratio is 0.999, and 0 of 21 pieces fall below
  0.5 × control. VP's prediction (ratio 0.9–1.05) is a **HIT**.
- **The registered measure is close to saturated.** A 5th-percentile threshold with a ±3-vox search along the normal
  puts almost every vertex "on papyrus", so the test can only catch a surface that is mostly in air.
- **The secondary, absolute threshold shows a small, local dip.**
  - Band vertices are on papyrus at 0.940, against 0.994 for controls.
  - Piece 11 is at 0.57 (control 0.99) and piece 13 at 0.84. The other 19 are ≥ 0.91.
  - Piece 11 is the one place where a stretch of the band lies off bright material. Even there it stays above half of
    control.
- **Consequence (registered):** build the page-5-only masked deck for Thomas (`deck_p5/`, BUILD_NOTES below).

## Page-5 masked deck: results
Sequence:
1. allocation recorded in 040f8c2c;
2. deck and sealed key hash in e73dc3c8 (7ccc4864…);
3. Thomas's responses committed unchanged in 6b24e985 (sha256 4318010d…). The export is 17:21:36Z, 40/40 answered.
   Conditions stated by the reader: "no". Median answer time is about 5 s.
4. Then the key, `unsealed_p5/key.json`, whose sha256 equals `keyhash_p5.txt`.

Score: `score_p5.py` → `score_p5.json`.
- P5B used 19 frames at 25/50/75% along the 8 longest pieces (5 of the 24 fixed positions had no acceptable frame
  within ±10 cells) plus 9 random along-piece frames.

| group | n | different | same | can't tell | "different" rate (Wilson 95%) |
|---|---|---|---|---|---|
| P5B: page-5 boundary pieces | 28 | **17** | 8 | 3 | 0.61 (0.42–0.76) |
| P5C: plain controls | 12 | 0 | 12 | 0 | 0.00 (0–0.24) |

- **Deck 3's H4 on page 5: NOT met.** P5B is 17/28 = 0.61, below the required 2/3 (19/28), while P5C is 0/12. It
  misses by two frames. d′ = 2.03 (log-linear).
- **VP's prediction (H4 holds) is a MISS.**
- **The boundary is not uniform by piece.** Per piece, P5B answers (different / same / can't tell):
  - consistently "different": pieces 1, 3, 5 (3/0/0 each), 11, 12, 17, 20 (1 each);
  - "same": piece 6 (0/2/0), 8, 16;
  - mixed: pieces 0, 2, 10;
  - "can't tell" on piece 4 (both frames), with notes "right/left not really on a sheet".
  - Three notes say one side of the line is "not really on a sheet" (pieces 2 and 4). This is the reader's remark,
    not a measurement. It sits alongside F2's absolute-threshold dip, which is at other pieces (11, 13).
- **Reading.**
  - On page 5, the reader separates boundary frames from controls clearly: 17/28 against 0/12.
  - But about a third of the boundary frames look like the same sheet to him. So page 5's boundary is a switch along
    some pieces (1, 3, 5) and not along others (6, 8, 16), rather than one switch.
  - Deck 2 (8/9 on page 5) and deck 3 (pooled pages) had suggested a cleaner switch. This deck samples page 5's
    pieces more evenly and does not support that.
- **For CLAIMS (LEAD decides):**
  - "On page 5, one blind reader judged 17 of 28 masked boundary frames 'different sheet' and 0 of 12 controls
    (registered rule ≥ 2/3: not met)."
  - The page-5 switch claim is therefore limited to the pieces with consistent answers.
  - This is one reader, not quotable alone.

## RULING 18:35 (items 1–3), recorded
- **Page-5 registered rule: MISS**, 17/28 against the required 19. A "17/25 excluding can't-tells" version is post
  hoc; it is not used anywhere, and this file never used it.
- **Interpretation (not a result):** the decks control false "different" but not distinct sheets pressed together, so
  17/28 is a lower bound on page-5 switching.
- **Page 5 stays UNRESOLVED:** a mixed pattern by piece. The per-piece split above (1/3/5 against 6/8/16) is
  descriptive only: post hoc, about 2 frames each, with no per-piece claim.
