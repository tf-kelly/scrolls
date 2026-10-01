# F1b: index turn changes, two colours (VP-M44 item 2). Pre-registration

Committed before any frame is drawn.
- **Turn-change frames (TC, 20):**
  - Pairs of indexed Scroll 4 patches with vertices within 4 vox of each other, whose per-vertex index windings w_v at
    the contact differ by exactly 1. These are the same contact definition and candidate source (pass-1 bins) as
    F1's straddling group.
  - Uniform draw over candidate pairs (seed 20260932). F1's 10 straddling pairs are excluded.
- **Same-winding frames (SW, 10):**
  - Pairs with contact ≤ 4 vox and equal w_v at the contact (expected answer "same").
  - Drawn the same way from bins with |Δ median r| ≤ 4 and Δw = 0.
- **Frames:**
  - As F1: 251 × 121 vox, ±125 along and ±60 across, centred on the contact vertex, horizontal from A's side to B's.
  - Patch A is drawn solid yellow, patch B dashed cyan (dashes 6 px on, 4 px off), so both are visible where they
    coincide.
  - Each patch's line must cross ≥ 20% of the frame, and their union ≥ 60%.
  - One pooled window; the order is shuffled; the key is sealed and its hash committed before reading.
- **Question:** "Are the yellow and the cyan line on the same sheet, or on different sheets?"
  - Answers: same / different / can't tell.
  - Conditions are stated first; no going back; zoom at most 2×.
- **Registered rule (COORD's, with LEAD's gap closed as 20 turn-change frames):** "different" on ≥ 14/20 TC AND on
  ≤ 2/10 SW → the index's turn changes between touching patches are judged real at the reader's level.
  - Otherwise: not established.
  - If not read by 20:00 London: "design failed; not retested".
- **Prediction (VP):** TC "different" 8–15 of 20. From F1's notes, touching patches with windings one apart often
  branch onto separate sheets, but not always. SW "different" 0–2. **VP expects the rule to fail narrowly or pass
  narrowly;** no confident call.
