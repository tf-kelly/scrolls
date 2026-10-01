# pipeline9_filter

This tool applies our reference-free wrap numbering and majority-turn pruning to W. Stevens' pipeline9 outputs, then
writes the result back in pipeline9's own formats. Downstream pipeline9 assembly can use it unchanged.

## Formats

| file | read | written |
|---|---|---|
| `rel.csv` (aligner output, no header: `patch_a, patch_b, flip, affine…`) | yes | kept rows, **byte-identical**, input order |
| `badpatches_b.csv` (one id per line: pipeline9's exclusion list) | yes | input ids ∪ pruned patches |
| patches (tifxyz `patch_N/` or `N.bin`, zip or dir) | yes (`--patches`: ids, bbox areas) | not rewritten: pipeline9 excludes patches through `badpatches_b.csv` |
| `wrap_index.csv`, `removed_joins.csv` (with reason), `filter.json` | — | yes |

## Method (the "combined" / hybrid row of P1e)

1. **Joins.** `rel.csv` pairs minus flip=1-only pairs (`phase/x10/flip1_pairs.csv`).
2. **Wrap-index cuts, (iii-rf).** A join is kept when either end has no wrap index. Otherwise it is kept only when its
   cut-adjusted Q3c wrap difference is 0 and its direct measurement (`d_i`, else `d_ii`) is absent or 0. This is
   `phase/p1page/p1b_rf_joins.py`'s rule; the wrap index is contract §2's Q3c solve (`p1b_q3c_k.csv`).
3. **pipeline9 deletions.** Drop every join that touches a mode-b flagged patch.
4. **Pruning.** Majority-turn pruning by our continuous turn `k + θ/2π` (`phase/p1page/p1d_prune.py` `prune`, vendored
   unmodified).
5. **Metrics.** Pages and metrics come from `phase/tools/metrics.py`.

`--no-rf` skips step 2, which is P1d's "(ii) + pruning" row. `risk` applies contract §4.6: it removes joins flagged by
the frozen risk model.

```bash
pip install -e phase/tools/pipeline9_filter
pipeline9-filter slab2 --out /tmp/p9 --bootstrap                                  # the hybrid row on committed slab-2 data (~7 s)
pipeline9-filter hybrid --rel rel.csv --badpatches badpatches_b.csv --patches s4_good_patches.zip s4_bad_patches.zip --out DIR
pipeline9-filter risk --rel rel.csv --switch-risk switch_risk.csv --out DIR       # contract §4.6
```

## Reproduction

| row | this tool | committed | source |
|---|---|---|---|
| combined (hybrid), slab 2 | 8,007 joins, 23 pages, 0 pruned; 65.3247 cm² [60.4651, 70.3585], M1 0.8817 [0.8682, 0.8947], M2 0.9995 [0.9989, 1.0], M3 0.0918 [0.0, 0.2348] | identical, every digit | `phase/p1page/p1e_frontier.json`; `results/slab2_combined/filter.json` |
| combined, X6 labelling | M1 0.461 | P1f 46.1 % | `phase/notes/C1.md` P1f |
| (ii) + pruning, slab 2 (`--no-rf`) | 312 pruned, 23 pages, 61.3652 cm², M1 0.8781, M2 0.9992, M3 0.1141 | identical point values | `phase/p1page/p1d_prune.json` |
| fixture (0.1 cm² pages) | (ii) and (iii-rf) pages equal golden; combined: 433 joins, 27 pages, 6.67 cm² | new; no golden exists | `results/fixture_combined/filter.json` |

Notes on the reproduction:
- The (ii) + pruning intervals differ in the third digit because P1d drew all five variants' bootstraps from one
  shared `default_rng(0)` stream. P1e, and this tool, use a fresh stream per row.
- `rel.csv` is not stored for slab 2; its sha256 is in `results/*/rel.csv.sha256`. Regenerate it with the command above.

## Claim limit (contract §5.4, Amendment 1)

This README may claim only the per-point M2 gain, and only once P1g confirms it. P1g has not reported, so **no gain
is claimed.** The numbers above are reproductions of committed rows, not new evidence that the filter helps.

M1 cannot rank methods (§5.2): every residual cross-turn join in these variants is a contact-regime join where the
reference is inconsistent. The per-patch-layer labels use the reference's `k_ref`. They are scored against a
machine-assisted reconstruction, not ground truth.
