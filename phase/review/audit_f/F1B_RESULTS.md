# F1b: index turn changes between touching patches, two colours, results (VP-M44)

Sequence:
1. pre-registration 83499b8d;
2. builder fixes (CT retry, and a candidate list of 250) c925954a and 0f22a525, before any frame existed;
3. deck and sealed key hash a3077a3f (a2a9fd9f…);
4. Thomas's responses committed unchanged, 25537407 (sha256 ad63fa6b…). The export is 17:24:22Z, 30/30 answered,
   within the 20:00 London limit. Conditions stated by the reader: "no".
5. Then the key, `unsealed_f1b/key.json`, whose sha256 equals `keyhash_f1b.txt`.

Score: `score_f1b.py` → `score_f1b.json`.

| group | n | different | same | can't tell | "different" rate (Wilson 95%) |
|---|---|---|---|---|---|
| TC: touching patches, index windings differ by 1 | 20 | **12** | 7 | 1 | 0.60 (0.39–0.78) |
| SW: touching patches, same index winding | 10 | 0 | **10** | 0 | 0.00 (0–0.28) |

- **Registered rule (≥ 14/20 TC "different" AND ≤ 2/10 SW): NOT met.** TC is 12/20, two short. SW is 0/10.
- **VP's prediction** (TC 8–15, SW 0–2) is a **HIT**.
- **Post hoc** (not registered): the TC "different" rate exceeds SW's with one-sided Fisher p = 0.0015. The reader
  separates the two groups clearly. SW is perfect.
- **Reading.**
  - Where our index puts two touching patches one winding apart, the reader judged them on different sheets in 12 of
    20. That is the index's claim.
  - He judged them on the same sheet in 7 of 20, one noted "super tight so very difficult to tell". That is against
    the index at those contacts.
  - Where the index puts touching patches in the same winding, he judged 10/10 the same sheet.
  - So about a third of the index's turn changes between touching patches are not supported by this reader (7/20;
    95% CI 0.18–0.57). The index is not wrong everywhere a turn change sits.
  - This rate applies to contact points between patches with different windings (46,835 candidate pairs by bin
    medians, about 20% of which have a true ≤ 4-vox contact). It is not a rate over the index's area.
- **The "same" answers on TC are spread through the scroll** (w 4/3, 12/13 twice, 15/14, 18/19, 21/22, 22/23). There
  is no concentration at the outer windings.
- **For CLAIMS (LEAD decides):**
  - "At 20 randomly drawn contacts where our index assigns touching patches to adjacent windings, one blind reader
    judged the two patches on different sheets in 12 and on the same sheet in 7 (registered ≥ 14/20: not met); at 10
    same-winding contacts, 10 same."
  - One reader, one sitting; not quotable alone.

## RULING 18:35 and the seam question (item 5)
**Ruling items 1, 2 and 6, recorded.**
- F1b's registered rule is a **MISS**: 12/20 against the required 14.
- **Interpretation (not a result):**
  - The decks control false "different" answers but not distinct sheets pressed together.
  - So "≥ 12/20 supported, ≤ 7/20 not": 7/20 is an upper bound on unsupported index turn changes at contacts.
- **Report placement:** an honest limitation of the index, in the fits/limits section next to outer windings
  w038–040 → 28. The 7 are spread through the scroll, not concentrated in the outer windings.

**Item 5: were contacts near the index's seam excluded? No.**
- The F1b draw did not exclude contacts near the per-turn winding increment. That increment is V1's cut at θ = 0
  about V1-15's umbilicus, where w_v steps by 1 along a sheet.
- `f1b_seam_check.json` gives each TC contact's angle from the seam and its arc distance at its radius.
- **Seam zone (stated now, post hoc):** within one frame half-width of the cut, 125 vox of arc.
- **Of the 7 "same" answers, 1 lies in the seam zone:** 63c6acb0, w 21/22, θ = 5.7°, 119 vox of arc from the cut.
  Its note is "super tight so very difficult to tell".
- The next nearest "same" is 530fbb16 at 18.2° (370 vox), outside the zone. The other 5 "same" are 35–178° from the
  seam.
- No "different" answer lies in the zone.
- **Post hoc, seam-zone frame removed:** 12/19 different, 6/19 same. The registered 12/20 stands.
