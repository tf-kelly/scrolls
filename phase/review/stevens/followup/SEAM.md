# COORD 02:45 seam check: S1, S2 (VP, 02:00Z)

Inputs: the VP_DUMP from SCALE's quilt2 rerun (quilt2_vpdump.py, handedness s = 1, reproduces 302.59 / 315.66 / 0.914),
Stevens' tifxyz pages, the tranche umbilicus, d1_main.json. Scripts: `seam_check.py` (S1, S2 as asked) and
`seam_unwrap.py` (S2 with theta unwrapped along the sheet). Outputs: `seam_check.json`, `seam_unwrap.json`.
No flipbook answer has been opened or scored.

## How quilt2 handles the seam
theta = atan2 about the umbilicus in [0, 2 pi). The seam is at theta = 0 for both the index lookup and the page. The
sheet key is q = w - floor(Theta / 2 pi), where Theta is the page's unwrapped angle (Theta = theta mod 2 pi). This
equals the continuous coordinate w + theta / 2 pi minus Theta / 2 pi. So q is already the seam-corrected comparison:
a correct sheet keeps one q across the seam. S2's "continuous coordinate" key equals q identically; the maximum
difference is 0 on all ten pages.

## S1: do D1 boundaries lie on the seam?
The index seam was measured, not assumed. On the one-sheet pages (3, 4, 6, 7, 8, 9), q steps at 0-3 of the 591-3619
grid edges that cross theta = 0. The raw integer w does step there: raw w changes minus q changes match the number of
seam-crossing edges. The index seam is therefore at theta = 0, and q absorbs it.

| page | boundary points within +-5 deg of seam | on seam (>= 80%) | D4' piece 1 | D4' piece 2 |
|---|---|---|---|---|
| 0 | 7.8% | n | 29.7% (theta 0-360, median 336) n | 0% (134-194 deg) n |
| 1 | 9.1% | n | 0% (82-140 deg) n | 0% (10-97 deg) n |
| 2 | 0% | n | 0% n | 0% n |
| 5 | 7.0% | n | 0% n | 0% n |

A uniform spread would put 2.8% of points within +-5 deg of the seam. **S1: no page's boundary is on the seam.**

## S2: one-sheet share (matched vertices on the modal key)
| page | raw integer w | quilt2 q (= continuous) | q' (theta unwrapped along the sheet) |
|---|---|---|---|
| 0 | 20.3% | 67.1% | 67.5% |
| 1 | 18.4% | 36.7% | 86.2% |
| 2 | 66.8% | 67.0% | 67.6% |
| 3 | 60.4% | 99.7% | 99.7% |
| 4 | 45.3% | 99.3% | 99.4% |
| 5 | 90.8% | 80.7% | 80.7% |
| 6 | 47.6% | 99.8% | 99.8% |
| 7 | 45.9% | 99.8% | 99.8% |
| 8 | 50.2% | 99.9% | 99.9% |
| 9 | 39.9% | 99.4% | 99.0% |

A comparison on raw integer windings would have shown spurious splits on every page, so Thomas's concern is right in
principle. quilt2 does not compare raw integer windings.

## A related artefact that is real: quilt2's unwrap branch cut
quilt2 unwraps Theta from a per-row (or per-column) mean angle, Theta = base + wrap(theta - base). Where a row's
angles span more than pi, Theta jumps by 2 pi between grid neighbours while theta does not. q then steps by 1 on a
continuous sheet. This is the same failure Thomas described, but at a branch cut rather than at the seam.
Branch-cut edges: page 0 1198, page 1 12740, page 2 598, page 3 234, page 4 210, page 9 337, others 0-40.

`seam_unwrap.py` unwraps theta along the page grid instead: a spanning tree over valid neighbours, summing wrapped
angle steps. The grid has 18-107 disconnected islands. Each island takes the whole-turn offset that best matches
quilt2's Theta, because that is the only link across gaps. A first run without this offset gave arbitrary island
offsets and spurious splits on pages 3, 4 and 6; it was discarded, not reported.

| page | D1 minority, q | minority, q' | D4' piece 1 still a boundary under q' | piece 2 | pieces near a quilt2 branch cut |
|---|---|---|---|---|---|
| 0 | 44.74 cm2 | 44.10 cm2 | yes (100%) | **no (0%)** | piece 2: 99.7% |
| 1 | 42.31 cm2 | 13.40 cm2 | **no (0%)** | **no (0%)** | both: 100% |
| 2 | 8.92 cm2 | 8.57 cm2 | yes | yes | 0% |
| 5 | 3.25 cm2 | 3.25 cm2 | yes | yes | 0% |

Caveats:
- Page 1 keeps 3368 grid edges where even the along-sheet unwrap jumps by more than pi, near row 2381, col 4259.
  Its grid there has loops that wind around the axis, or the umbilicus is off near this core page. Its 13.4 cm2 is
  not clean either. Pages 3, 8 and 9 have 24-312 such edges, with no effect on their shares.
- The island offset uses quilt2's Theta across gaps, so an error there would carry over.

## Consequences (for COORD; nothing changed in CLAIMS or the draft)
1. There are no seam boundaries, so under S3 no D1 boundary is a seam artefact.
2. Branch-cut boundaries are artefacts in the same sense: page 0 piece 2 (56 of the 149 page 0 frames) and page 1
   pieces 1-2 (all 178 page 1 frames). Under S3's logic they carry no disagreement. Before any answer is opened, VP
   proposes that COORD choose one of:
   (a) drop them from scoring, or
   (b) score them as artefact controls, where "same count" is the expected outcome and a "differs by one" verdict
       would count against the method.
   Thomas has not been told which pieces these are.
3. Quilt v2 figures that include page 1 overstate the disagreement. Page 1 goes from 42.3 to about 13.4 cm2, and that
   figure carries caveats. "4 pages straddle" and the 6/10 figure need recomputing with q' before any use. VP has not
   recomputed SCALE's b/c/d outputs.
4. The flipbook adds pages 2 and 5, whose boundaries are real under both keys. Page 1 is rendered and committed but
   held from the reader page pending COORD.
