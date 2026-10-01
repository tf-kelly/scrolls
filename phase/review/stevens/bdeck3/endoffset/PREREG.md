# Deck 3 end-offset check: pre-registration (COORD 05:02, VP-M28 item 2)

Committed before `end_offset.py` is run. Geometry only: no CT, no reader data.

## Measure
For each deck-3 frame, the frame geometry is recomputed from the unsealed key: page, centre (row, col) and in-page
direction, with the same plane as `build_bdeck3.py`. His line's segments are recomputed with
`section_geometry.surface_segments`. Frame coordinates are u across (0–300 vox, centre 150) and v down (0–120 vox).

- **Left end:** of the visible left-side segment points (u ≤ 100 and 0 ≤ v ≤ 120), the point with the largest u.
  **Right end:** of the visible right-side points (u ≥ 200), the point with the smallest u. If several branches
  reach the same u within 1 vox, the one nearest the frame's vertical centre is taken.
- **Offset (primary)** = |v_right_end − v_left_end| in vox. This is the height step the reader could see between
  the two visible ends.
- **Secondary (descriptive)** = |v_right_end − v_extrap|, where v_extrap is the left side's last 20 vox of line
  fitted linearly and extended to u = 200.

## Rule (COORD's)
Classes are as in H4:
- real = R02 (14 frames);
- control = ART + DP (12 frames).

AUC is the probability that a real frame's offset exceeds a control frame's, with ties counted as half. A threshold
sweep is also reported.
- **AUC ≥ 0.9:** the limit is restated as "line-end offset is a sufficient cue; sheet continuity per se not
  isolated".
- **AUC < 0.9:** no limit.

## Also reported (descriptive, no rule)
- Offsets for R5, P1R and DD.
- Whether the reader's "different" answers track the offset within R02 + ART + DP.
