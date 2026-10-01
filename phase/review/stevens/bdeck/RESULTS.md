# Blind switch / no-switch deck: results (COORD 03:14)

Sequence, all on `claude/int-vp`:
- pre-registration, deck, order and key sha256 (dcbc870);
- Thomas's responses, committed unchanged (c584e4c; export 02:29:21Z; 30/30 answered; conditions stated by the
  reader: model output seen "no");
- then the key, `unsealed/key.json`. Its sha256 is 19ed1869…f246006, equal to `keyhash.txt`.

Score: `score_bdeck.py` → `score_bdeck.json`.

## Ruling against PREREG.md
| | switch | no switch | can't tell | n |
|---|---|---|---|---|
| real boundary | **8** | 3 | 1 | 12 |
| artefact boundary (quilt2 branch cut) | **0** | 6 | 0 | 6 |
| decoy (≥ 100 vox from any boundary) | **1** | 10 | 1 | 12 |

- Hit rate H = 8/12 = 0.667; Wilson 95% interval 0.39–0.86.
- False-alarm rate F = 1/18 = 0.056; interval 0.01–0.26.
- d′ (log-linear) = 1.81.
- Rule: H ≥ 2/3 AND F ≤ 1/4. **The switch finding stands, exactly at the hit threshold.** One fewer "switch" on the
  real frames would have failed it.
- With can't-tell excluded: H = 8/11 (0.73), F = 1/17 (0.06).
- Fisher exact, one-sided, real vs other: p = 0.0006. This is not pre-registered; it is reported only as context.
- False alarms by kind: artefact 0/6, decoy 1/12. The one decoy "switch" (page 2) carried the note "very tight".

## Per page (post hoc, descriptive; no rule attached — COORD 03:52)
| page | real | artefact | decoy |
|---|---|---|---|
| 0 | 2/2 switch (piece 1) | 0/2 (piece 2) | 0/4 |
| 1 | — | 0/4 (pieces 1 and 2) | — |
| 2 | 4/4 switch (pieces 1 and 2) | — | 1/4 |
| 5 | 2/6 switch (piece 1: 2 switch, 1 no switch, 1 can't tell; piece 2: 0/2) | — | 0/4 |

- **Pages 0 and 2:** every real-boundary frame was judged a switch.
- **Page 5:** mostly not a switch. Its notes read "not completely clear", "the line wanders a bit" and "mostly off any
  surface". So at page 5's boundaries the reader mostly saw his page stay on one sheet. That points to our index,
  or to where his line sits, rather than to a sheet change in his page. At 2 + 4 frames this does not settle page 5.
- **Artefact boundaries:** 0/6 switch. This is blind agreement with SEAM.md: where our key changed only because of
  quilt2's unwrap branch cut, the reader saw no switch. It also argues against the confound stated in advance, that
  a reader might answer "switch" to any frame near a boundary.

## What this supports (for LEAD / COORD; nothing added to CLAIMS or the draft)
Suggested wording: "In a blind deck of 30 CT cross-sections, one reader judged Stevens' page to switch sheet on 8 of
12 frames across our index's disagreement boundaries, on 0 of 6 across index-only artefact boundaries and on 1 of 12
away from any boundary; the pre-registered rule (hit ≥ 2/3, false alarm ≤ 1/4) was met at its threshold."
- Supporting only.
- One reader. It is blind to class, and the reader did not see the index assignment.
- The frames are machine-generated sections of a machine-generated mesh.

How this bears on areas (minority areas with the angle unwrapped along the sheet, from `seam_unwrap.json`):
- page 0: 44.1 cm², the switch supported at piece 1;
- page 2: 8.6 cm², supported;
- page 5: 3.25 cm², mostly not supported;
- page 1: the remaining 13.4 cm² was **not tested**. Its deck frames were the artefact pieces only.

No page's area goes into +315.7 without this outcome beside it (D5).

## Limits
- 30 frames and one reader. The hit rate sits on its threshold.
- Answer times were 3–41 s per frame, and 5 min 40 s for the whole deck.
- Real frames come from 5 pieces on 3 pages, so they are not independent samples of "a boundary".
- The flipbook sittings before the deck were non-blind and exploratory (B4). The deck's frames are new positions, so
  none was an image Thomas had seen, but he had seen neighbouring sections of page 0 piece 1.

## Next, in the pre-registered reveal order (B5)
Superseded by COORD 03:52: D2 and D3 may be opened now; P3 runs in parallel (see below). D2 and
D3 have not been opened.

## COORD 03:52 rulings (recorded)
- The deck is accepted as scored: rule met at threshold (8/12 real, 0/6 artefact, 1/12 decoy; d′ 1.81).
- **The per-page split is descriptive and post hoc:** pages 0 + 2 6/6; page 5 2/6.
- **Page 5 is recorded as:** "not supported; reader notes surface off the papyrus; hypothesis: his mesh leaves the
  sheet and the comparison matches the neighbouring sheet — untested". Blind deck 2 (H2) tests this.
- The hindsight note stays separate (`post_unblinding_notes.md`), and the score is unchanged.
- **The non-blind flipbook impression for page 5 was not borne out blind.** On 03:12 Thomas said "2 and 5 also show
  lots of sheet switching". Blind, page 5 went 2/6. The verbatim notes are in `flipbook_notes.md`.
- **D5 areas:** page 0 44.1 cm², supported; page 2 8.6 cm², supported; page 5 3.25 cm², not supported; page 1
  13.4 cm², untested.

## COORD 04:25 (recorded)
- The page 5 wording from 03:52 ("not supported …") is **withdrawn**. New wording: **"page 5: 2/6 (deck 1), 8/9
  (deck 2); mixed"**.
- Deck 3 (masked middle) tests the shape-cue limit. Decks 1 and 2 stand as reported.
