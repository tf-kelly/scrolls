# Blind deck 3 (masked middle): results (COORD 04:25)

Sequence, all on `claude/int-vp`:
- pre-registration: c0823fb (PREREG sha256 40f0ad95…);
- deck and sealed key hash: 5e3f68e (d0b34d59…);
- Thomas's responses, committed unchanged: 0d6b352. Export 03:57:09Z; 44/44 answered; conditions stated by the
  reader: model output seen "no";
- then the key, `unsealed/key.json`. Its sha256 is d0b34d59…6154702a, equal to `keyhash.txt`.

Score: `score_bdeck3.py` → `score_bdeck3.json`.

## Answers by group
| group | n | same | different | can't tell | "different" rate (Wilson 95%) | median s |
|---|---|---|---|---|---|---|
| R02 real, pages 0 + 2 | 14 | 1 | **13** | 0 | 0.93 (0.69–0.99) | 4.7 |
| R5 real, page 5 | 8 | 3 | 2 | **3** | 0.25 (0.07–0.59) | **14.5** |
| P1R page 1 remainder | 5 | **5** | 0 | 0 | 0.00 (0–0.43) | 3.2 |
| ART artefact | 7 | 7 | 0 | 0 | 0.00 (0–0.35) | 3.4 |
| DD decoy on deformed mesh | 5 | 4 | 1 | 0 | 0.20 (0.04–0.62) | 4.6 |
| DP plain decoy | 5 | 5 | 0 | 0 | 0.00 (0–0.43) | 3.7 |

The median across all 44 frames was 4.5 s.

## Ruling against PREREG
- **H4 HOLDS.** "Different sheet" on R02 is 13/14 (0.93 ≥ 2/3). On ART + DP it is 0/12 (0 ≤ 1/4).
- d′ (log-linear) = 3.05.
- Can't-tell on R02 is 0/14, not over 1/2.
- **Consequence, as COORD set it in advance:** the shape-cue limit is removed from CLAIMS. With the line hidden where
  a kink would be, the reader still separated real boundaries from controls.

## Descriptive (no rule)
- **H5, P1R:** "same sheet" on 5/5. With deck 2's 0/6 switch, page 1's remaining boundary has looked like one sheet
  at 11/11 sampled points. At those points our index assigns two windings to what the reader sees as one sheet.
  That points to our index being wrong there, not his page. P3 found the mesh along this boundary only mildly more
  deformed than its controls (1.46×, below the 2× rule).
- **DD:** "different" on 1/5, with 4 "same". Deformed mesh away from our boundaries was mostly judged one sheet.
  That argues against the reader answering from mesh deformation alone. The one "different" (e789cb51, page 2, P3 share 0.38) is not
  interpretable on its own: it could be a reader cue, or a switch our index does not flag.
- **R5 (page 5):** mixed, and notably slow.
  - Answers: "different" 2, "same" 3, can't tell 3. The median time was 14.5 s, against about 4 s elsewhere.
  - 6 of 8 notes describe the line off the papyrus: "off the sheet entirely on the right", "right on no sheet",
    "wanders off the sheet", "left one wanders almost completely off", "mostly off sheet on left side", "multiple
    lines on right hand side".
  - Deck 1's page 5 picture ("his mesh leaves the sheet") reappears here, now with the middle hidden. Deck 2's 8/9
    "switch" on page 5 may reflect that question's framing: a line that leaves a sheet was answerable there as
    "switches".
  - This is descriptive, not a test. Page 5 stays "mixed".
- **R02 misses and notes:** 1 "same" (e784eaeb, page 0 piece 1: "I think but hard to tell bc left wanders"). One
  "different" carried the note "but not 100% clear, might just be wandering" (b1f99163, page 0 piece 1).

## All three decks (each reported; none replaces another)
| group | deck 1 (switch) | deck 2 (switch) | deck 3 (different sheet) |
|---|---|---|---|
| real, pages 0 + 2 | 6/6 | 16/16 | 13/14 |
| real, page 5 | 2/6 | 8/9 | 2/8 (3 can't tell) |
| artefact | 0/6 | 0/10 | 0/7 |
| plain decoys | 1/12 | 0/17 | 0/5 |
| deformed-mesh decoys | — | — | 1/5 |
| page 1 remainder | — | 0/6 | 0/5 (5/5 same) |

## Limits
- **One reader.** He knew the composition and results of decks 1 and 2.
- **Two builds were discarded** before anyone saw them, and a visibility filter was added. See BUILD_NOTES; the
  filter rejected 7 boundary candidates and 0 decoys.
- **A residual cue remains, not controlled:** the height offset between the two visible line ends at x = ±50 vox. A
  line that changes sheet usually ends at a different height, so the offset carries sheet information. But curvature
  alone can offset the ends. A post hoc check would measure that offset per frame and ask whether it alone separates
  the classes. It is not done.
- **Machine-generated inputs.** The frames are sections of a machine-generated mesh; agent review is not human
  adjudication.

## End-offset check (COORD 05:02; pre-registration a955dde; `endoffset/end_offset.json`)
- **Offset alone does not separate real from control frames: AUC 0.52.** Real = R02, 14 frames. Control = ART + DP,
  12 frames.
  - Median offsets: R02 7.0 vox, ART 4.7 vox, DP 7.8 vox.
  - The secondary measure (offset from the left side's linear extrapolation) gives AUC 0.67.
- **Rule** (AUC ≥ 0.9 → the limit is restated): not met. **No limit.**
- **Descriptive:** the reader's "different" and "same" answers also do not track the offset (AUC 0.51 within
  R02 + ART + DP).
- The residual-cue limit in the section above is therefore closed for line-end offset.

## COORD 05:02 wording (recorded)
- **H4 holds.** The shape-cue limit is removed for pages 0 and 2. The deformed-mesh decoys (4/5 same) are noted as
  supporting. LEAD notes that CLAIMS never carried the limit. In VP's files the limit appears only in deck 2's
  RESULTS, which stays as recorded history, now answered by decks 3 and this check.
- **Page 1 remainder:** "our index disagrees with page 1 over N cm²; sampled sections show one sheet; treated as an
  index error".
  - N depends on the page-key implementation: 13.40 cm² (VP, `seam_unwrap.py`); 9.18 cm² before and 9.11 cm² after
    V1's drop of ambiguous crossing constraints (V1 P1FIX, e37767ee).
  - LEAD suggests "9.1–13.4 cm² (two page-key implementations)". VP agrees, and names the difference: VP counts all
    vertices, nearest-matched fill included; V1 counts its own matched vertices in the largest island.
- **Page 5:** "10/15 switch across decks 1–2 under the switch/stay question; 2/8 different under the masked
  question; reader notes the surface leaves the papyrus along this boundary in decks 1 and 3".
