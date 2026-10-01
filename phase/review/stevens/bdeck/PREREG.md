# Blind switch / no-switch deck (COORD 03:14, B1-B5): pre-registration

This file, `keyhash.txt` and `deck.json` are committed in one commit before Thomas opens the deck. The sealed key
(`key.json`) stays outside git until his responses are committed unchanged.

## Why
Thomas declined per-frame counts. Whether his page switches sheet at our index's boundaries is tested instead by a
blind judgement on frames whose class he cannot see.

## Deck (B1, B2)
- **30 frames.** The geometry is the same as the D4' flipbook: a CT section at level 0 across the page, ±150 vox in
  the page direction by ±60 vox along the page normal, 1 px/voxel shown ×2. His surface is drawn thin in yellow,
  placed numerically by `section_geometry.surface_segments`.
- **No ticks, no page or piece labels, no index colours.** Random 8-hex ids, shuffled once.
- **One contrast window for the whole deck** (pooled p1–p99 of the 30 frames). This differs from D4', which used one
  window per page: a per-page window would let contrast identify the page, and page 1 frames are all artefacts.
- **Question, per frame:** "Does the yellow line stay on one sheet from left edge to right edge?" Answer: switch /
  no switch / can't tell, plus an optional note. One frame at a time, no going back, zoom 2× at most.
- **Composition (not disclosed to the reader):**
  - **Real, 12.** Across the D1 main-boundary pieces the index keeps under both keys: page 0 piece 1 (2), page 2
    pieces 1 and 2 (2 + 2), page 5 pieces 1 and 2 (4 + 2). Frames are split in proportion to piece length by largest
    remainder.
  - **Artefact, 6.** Across the pieces SEAM.md (8ff6280) shows to be quilt2 unwrap branch cuts: page 0 piece 2 (2),
    page 1 pieces 1 and 2 (2 + 2).
  - **Decoy, 12.** 4 each from pages 0, 2 and 5. Each is centred at least 100 vox from every D1 boundary under both q
    and the unwrapped q', and points in a random in-page direction.
- **Placement** (seed 20260930, full rule in `build_bdeck.py`):
  - Boundary frames sit midway between flipbook positions, so no deck image is a flipbook image.
  - Frames on one piece are at least 100 vox apart.
  - Page 0 piece 1 frames lie at least 100 vox past the last flipbook frame Thomas answered (f013). The flipbook's
    storage records no answers anywhere else.
  - Every frame has at least 90% valid page along its line.
- **Page 0 piece 2 is kept as a blind control** (B4). Thomas has not been told that it is an artefact.

## Outcome rule (B3, fixed before any response)
With n_real = 12 and n_other = 18 (6 artefact + 12 decoy):
- hit rate H = (real frames answered "switch") / 12
- false-alarm rate F = (artefact + decoy frames answered "switch") / 18
- "Can't tell" counts as not-switch in both rates.

**The switch finding stands iff H ≥ 2/3 (at least 8 of 12) AND F ≤ 1/4 (at most 4 of 18).** Otherwise it does not
stand.

Also reported, none of which changes the ruling:
- d′ = z(H') − z(F'), log-linear corrected: H' = (hits + 0.5) / (12 + 1), F' = (FA + 0.5) / (18 + 1);
- can't-tell counts per class;
- false alarms separately for artefact (out of 6) and decoy (out of 12);
- the same two rates with can't-tell excluded from the denominators;
- per-page breakdown.

Scoring script: `score_bdeck.py`, committed here, reads the responses and the unsealed key and applies this rule.

## Earlier flipbook observations (B4)
These are exploratory and non-blind. Thomas's 03:01 and 03:12 descriptions go into `flipbook_notes.md` verbatim as
he wrote them. No counts are required. They are not scored.

## Reveal order (B5)
1. The deck is scored: responses committed, then the key.
2. P3 fold check.
3. Only then are D2 (V1's LP contradiction flags) and D3 (SCALE's arm_b side) opened.

Reported as a single reader. The reader did not see the index assignment, and the deck is blind to class.

## Limits stated in advance
- This is one reader and 30 frames, so the power is low: only a large difference between classes can meet the rule.
- Decoys are far from boundaries, and boundary frames differ from decoys in whatever way boundaries look different
  in CT: a reader could answer "switch" to "busy" frames. The artefact class is the control for that: artefact
  boundaries are index-only, and his page is continuous across them.
- The yellow line's position is numerical. Frames are machine-generated; the page is a machine-generated mesh, not
  ground truth.
