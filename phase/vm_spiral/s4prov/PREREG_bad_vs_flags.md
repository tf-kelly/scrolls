# Stevens "bad" patches vs our index's contradiction flags: pre-registration (COORD 15:16, SessB)

This file is committed before any flag is joined to the Stevens labels. At the time of commit SessB has the patch-id lists
and the flag file's hash, and nothing joining the two.

## Inputs (pinned)
- **Stevens' labels.** These are the two public zips at `https://dl.ash2txt.org/community-uploads/will/`, listed by
  `zip_listing.py` (central directory only).
  - `s4_good_patches.zip`: 1,699,975,582 B, Last-Modified 31 Jul 2026 21:05:40 GMT, 47,797 patch folders, each with
    x/y/z.tif and meta.json. The ids are in `stevens_good_ids.txt` (sha256 of the sorted list 78711257…).
  - `s4_bad_patches.zip`: 344,382,019 B, Last-Modified 31 Jul 2026 20:58:09 GMT, 9,171 patch folders. The ids are in
    `stevens_bad_ids.txt` (61469fa0…).
  - The two id sets are disjoint, and their union is 56,968.
  - **`s4_hed_patches.zip` does not exist.** It returns HTTP 404 at 15:20 London, and the directory listing has no
    such file (X1 found the same). The 9,171 "bad" set is therefore `s4_bad_patches.zip`. It is the same count the
    coordinator gives for "hed", so "hed" is taken as a name for this file.
- **Our index.** This is `tranche_s4_whole`, SessA-15's whole-scroll `wrap_index.csv` (sha256 1c0b7d30…), with 56,934 patches.
- **Flags.** A patch is "flagged" iff it appears as `patch_a` or `patch_b` in any row of the named flag file.
  - The default is SessA-15 `whole/unsatisfied.csv` (<branch> d93d9e20, sha256 6694e964…). It is byte-identical to SessJ's
    `bundle/flags/unsatisfied_whole.csv`, and it is the rule SessJ's quilt used to drop "flagged patches"
    (`quilt.py` lines 276–279).
  - Item 2 of the message is SessA's call. If SessA names a different file, that file is used unchanged with the same rule,
    and this default is reported as a secondary row.

## Population
- The 2×2 table is over the **56,934 patches in the index**.
- The 34 union patches that are absent from the index are listed in `not_in_index_34.txt` (33 good, 1 bad). They are
  reported as a separate row and are not counted as unflagged.

## Prediction (coordinator's, registered here verbatim in substance)
- **The prediction holds iff both of these are true:**
  - P(flagged | Stevens bad) ≥ 0.40;
  - P(flagged | Stevens good) < 0.10.
- Denominators are bad and good patches in the index.
- SessB's own note, not part of the rule: flags attach to *pairs*, so a patch is flagged when any of its joins is
  unsatisfied. A patch's number of joins therefore raises its chance of a flag irrespective of quality.
  - The table is also reported stratified by join-count quartile (joins = edges in SessA-12 `solve_edges.json`).
  - This stratification does not change the verdict.

## Area figures (reported, no threshold)
Both figures are for SessJ's whole-scroll quilt: the ARC run of 29 Sep, arm a, 648.325 cm² trace and 17.506 cm² conflict
with flagged patches dropped.
- **Share of trace area from Stevens bad patches.** These are trace cells (label 1) whose contributing unflagged
  patches include at least one bad patch. Two shares are reported:
  - "any bad contributor";
  - "all contributors bad".
- **Conflict area inside vs outside bad patches.** A conflict cell (label 3) is "inside" when its extreme patch pair
  includes a bad patch.
  - The same split is reported for the all-patch conflict (32.595 cm²).
- These need the quilt's per-cell patch membership. If the returned quilt outputs lack it, SessB re-runs `quilt.py`
  unchanged with a membership dump. That is a CPU job through the launcher, dry-run gated. If this is needed, SessB says
  so before launching.

Agent analysis. Stevens' labels are his own machine-and-review labels, not ground truth. Our flags are machine output.
