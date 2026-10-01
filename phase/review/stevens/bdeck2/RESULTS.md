# Blind deck 2: results (COORD 03:54)

Sequence, all on `claude/int-vp`:
- pre-registration: 24df259 (PREREG sha256 d348e2b2…);
- deck and sealed key hash: aac7ba1 (31711f1f…);
- Thomas's responses, committed unchanged: 39627b9. Export 03:22:21Z; 58/58 answered; conditions stated by the
  reader: model output seen "no";
- then the key, `unsealed/key.json`. Its sha256 is 31711f1f…77e83a2, equal to `keyhash.txt`.

Score: `score_bdeck2.py` → `score_bdeck2.json`.

## Answers by group
| group | n | switches | stays | leaves papyrus | can't tell | switch rate (Wilson 95%) |
|---|---|---|---|---|---|---|
| R02 real, pages 0 + 2 | 16 | **16** | 0 | 0 | 0 | 1.00 (0.81–1.00) |
| R5 real, page 5 | 9 | **8** | 0 | 1 | 0 | 0.89 (0.57–0.98) |
| ART artefact | 10 | 0 | 10 | 0 | 0 | 0.00 (0–0.28) |
| DA decoy, pages 0/2/5 | 8 | 0 | 8 | 0 | 0 | 0.00 (0–0.32) |
| DB decoy, pages 3, 4, 6–9 | 9 | 0 | 9 | 0 | 0 | 0.00 (0–0.30) |
| UNK page 1 remaining boundary | 6 | 0 | 6 | 0 | 0 | 0.00 (0–0.39) |

## Rulings against PREREG
- **H1 (replication): HOLDS.** R02 switch rate 16/16 ≥ 2/3, and ART + DA + DB 0/27 ≤ 1/4. d′ (log-linear) = 3.99.
- **H2 (page 5 does not switch and leaves the papyrus): DOES NOT HOLD.** R5 switch rate 8/9, against ≤ 1/3 required.
  "Leaves the papyrus" 1/9, against ≥ 1/2 required. The one "leaves" answer carried the note "but no actual switch".
- **H3 (artefact control): HOLDS.** ART 0/10.
- **UNK (descriptive):** 0/6 switch, 6/6 stays. At the six sampled points on page 1's remaining boundary, the reader
  saw his page stay on one sheet.

## Deck 1 and deck 2 side by side (both reported; neither replaces the other)
| | deck 1 (6ec067a) | deck 2 |
|---|---|---|
| real, pages 0 + 2 | 6/6 switch | 16/16 switch |
| real, page 5 | 2/6 switch | 8/9 switch |
| artefact | 0/6 | 0/10 |
| decoy | 1/12 | 0/17 |
| page 1 remaining | — | 0/6 (stays) |

- **Page 5 disagrees between the decks:** 2/6 against 8/9. Pooled that is 10/15, but the pre-registered H2 (the
  deck-1 page 5 hypothesis) failed. COORD's 03:52 wording for page 5 ("not supported … hypothesis: his mesh leaves
  the sheet") is not borne out by deck 2.
- Differences between the decks that may matter:
  - the deck 2 question ("follow the yellow line") and its explicit "leaves the papyrus" option;
  - different positions along the page 5 pieces: deck 2 put 6 frames on piece 1 and 3 on piece 2, deck 1 put 4 and
    2;
  - the reader's experience after deck 1.
  These are not tested.

## What the deck does and does not establish
- **Established, blind to class:** at our index's real disagreement boundaries (pages 0, 2 and 5), one reader judged
  Stevens' page to switch sheet on 24 of 25 frames in deck 2. At index-only artefact boundaries, and away from any
  boundary, he judged it to stay on one sheet on 27 of 27.
- **Not established: that the reader is judging the sheets rather than the line's shape.**
  - Real-boundary frames are centred where the mesh is more deformed. P3 found the fold/stretch rate higher in
    every real-boundary band than in its controls.
  - Artefact and decoy frames are not centred on deformation.
  - A reader who learned in deck 1 that "switch" frames tend to have a kink at the centre could separate the classes
    on the kink alone. The artefact control rules out "any index boundary looks like a switch". It does not rule out
    "a mesh kink looks like a switch".
  - A deck that controls for this needs decoys centred on equally deformed mesh away from any index boundary. P3's
    flags can select them.
- **Reader limits** (recorded in advance): one reader, not naive to the pages, who knew deck 1's composition and
  results. Answers were fast: 2–27 s each, 5 min 38 s for 58 frames. Agent review is not human adjudication. The
  frames are machine-generated sections of a machine-generated mesh.

## For D5 (areas; COORD's call on wording)
| page | area (along-sheet key) | deck 1 | deck 2 |
|---|---|---|---|
| 0 | 44.1 cm² | switch 2/2 (piece 1) | switch 5/5 (piece 1) |
| 2 | 8.6 cm² | switch 4/4 | switch 11/11 |
| 5 | 3.25 cm² | switch 2/6 | switch 8/9 |
| 1 | 13.4 cm² | untested | stays 0/6 switch (UNK, descriptive) |

## COORD 04:25 (recorded)
- Deck 2 is accepted as scored: H1 holds (16/16; controls 0/27; d′ 3.99); H3 holds (0/10).
- **H2 fails.** It was a coordinator-registered hypothesis and is recorded as the coordinator's miss.
- Page 5 wording: **"page 5: 2/6 (deck 1), 8/9 (deck 2); mixed"**. This replaces 03:52's "not supported".
- Page 1 remainder: 0/6 switch, descriptive. The shape-cue caveat applies to it equally.
- Deck 3 adds to decks 1 and 2 and replaces neither.
