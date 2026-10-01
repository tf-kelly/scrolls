# S3: Stevens' removals against our flags, blind deck by S2 cell: results (V1-M48; PREREG_S3.md 43563b6e)

Sequence:
1. registration 43563b6e;
2. deck and sealed key hash d0177195 (d522bb1d…);
3. Thomas's responses committed unchanged, 4f9d8fe2 (sha256 dc2ee2d2…). The export is 19:19:35Z, 40/40 answered.
   Conditions stated by the reader: "no". He left no notes.
4. Then the key, `unsealed/key.json`, whose sha256 equals `keyhash.txt`.

Score: `score_s3.py` → `score_s3.json`. As registered, there is no pass/fail.

| cell | n | yes (one sheet) | no | can't tell | "yes" rate (Wilson 95%) | VP prediction |
|---|---|---|---|---|---|---|
| BB: both flag it | 10 | 7 | 3 | 0 | 0.70 (0.40–0.89) | 5–9: hit |
| HO: his removal only | 10 | **6** | **4** | 0 | 0.60 (0.31–0.83) | 6–10: hit |
| OO: our flag only | 10 | 8 | 1 | 1 | 0.80 (0.49–0.94) | 6–10: hit |
| GG: neither | 10 | 8 | **2** | 0 | 0.80 (0.49–0.94) | 9–10: **miss** |

**Reading, descriptive, with n = 10 per cell:**
- **On the disagreements,** his-only patches drew 4 "no" and our-only patches 1 "no". The direction favours his
  removal list over our flags. But the difference is not significant (post hoc Fisher, two-sided, p = 0.30), and
  every interval overlaps.
- **Pooled by list** (post hoc):
  - by his list: 7/20 "no" among his removals against 3/20 among his kept;
  - by ours: 4/20 among our bad against 6/20 among our good.
  - Reader "no" tracks his list somewhat. It does not track ours: our "good" patches drew more "no" than our "bad"
    ones.
- **Both-good drew 2/10 "no".** That is below VP's prediction and in contrast with T1 (28/28) and F1's random cells
  (20/20).
  - The frame design is the same as T1's, a section through a patch centre. F1's frames were centred on random trace
    cells.
  - With n = 10, 2 "no" is within chance of a low true rate (95% CI 6–51% "no").
- **What the registration anticipated holds:** no cell is below 5/10. At patch centres, and with n = 10, the deck does
  not separate the two methods decisively.

**For CLAIMS (LEAD decides; one reader, not quotable alone):** "In a blind deck of 10 patch-centre sections per cell,
the reader judged the patch on one sheet in 7/10 (both lists flag), 6/10 (his removal only), 8/10 (our flag only)
and 8/10 (neither). Differences are within chance; the direction on the disagreements favours his list (4 vs 1 'not
one sheet')."
