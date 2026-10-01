# Licences

- Our code: MIT (`LICENSE`).
- **Derived from the PHerc 1667 complete-unwrapping mesh (arXiv:2606.29085), licensed CC BY-NC 4.0, not covered by
  MIT.** Attribution: arXiv:2606.29085. These files, or the named columns in them, are computed from that mesh:
  - `phase/data_small/fixture/reference_subset.npz` (upsampled reference vertices);
  - `phase/data_small/fixture/golden/wrap_index.csv`: columns `k_ref` and `k_ref_point_agreement`;
  - `phase/data_small/fixture/x6_pairs.csv`: column `truth`;
  - `phase/data_small/fixture/pair_features.csv`: column `truth`;
  - `phase/data_small/fixture/golden/switch_risk.csv`: column `x6_truth`;
  - `phase/data_small/fixture/x6_points.npz` (the reference-evaluated point pairs behind `x6_pairs.csv`);
  - `phase/data_small/fixture/golden/defects.csv`, `golden/expected_cross_turn_clusters.json` and
    `golden/pages_metrics.json` (scored against the reference).
- Fetched third-party data (W. Stevens' patches, CT) is not shipped; see
  `phase/data_small/fixture/fetch_fixture.py`.
- `data/segments_1667.txt` lists upstream segment ids only; the meshes are not shipped.
