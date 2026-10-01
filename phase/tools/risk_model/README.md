# Risk model v1 = the **switch score** (CONTRACT §3, Amendment 3 §A3.1)

- **What it is.** `risk_model_v1.joblib` gives the probability that a joined patch pair is a switch, i.e. that §2's
  wrap index changes between the two patches. Flag at the blind threshold 0.3293271860685008.
- **What it is not.** It is not an error, doubt or confidence estimate for the wrap index.
  - It is trained on `round(k_b − k_a) ≠ 0` from the same Q3c solve that produces the index, so it learns to agree with
    the index.
  - Against actual index disagreements with X6 it scores AUC 0.506 (ledger item-15).
  - **No error score exists.**
- Viewer and README text: **"flags mark where the index changes, not where it is doubtful."**
- The names `risk`, `max_risk` and `switch_risk.csv` are kept for format stability and mean switch score.
- Build: `build_risk_model.py`. Checks: `risk_model_v1.json` (ledger item-04). Environment pins:
  `phase/tools/requirements.txt` (scikit-learn 1.9.1 exact: the joblib file is a pickle).
