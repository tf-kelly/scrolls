#!/usr/bin/env python3
"""Contract risk model v1: the Q3c reference-free consensus X8 model, fitted once and frozen with a blind threshold.

Why this file exists: Q3c (<branch> 0f5aa76, phase/q3/q3c_deploy.py) trained this model only inside
its 4 outer folds and scored it at reference-matched thresholds. It committed no deployable model and no blind
threshold. The contract needs both, so this script builds them from Q3c's own functions, unchanged:

  labels     q3c_deploy.solve_consensus_labels(state, uniform_weight): uniform weights, axis from patch centroids,
             handedness by the lower LP objective; label = round(k_b - k_a) != 0. No reference input.
  rows       q3c_deploy.attach_labels_and_folds with Q3c's five label sources, i.e. the same 7,087 CV-eligible pairs.
  model      HistGradientBoostingClassifier(class_weight="balanced", random_state=8) on q3_part2.FEATURES (the
             all-NaN columns dropped exactly as Q3c), fitted on all 7,087 pairs with the reference-free label.
  threshold  blind: 4-fold (Q3c's patch-z folds) out-of-fold probabilities, threshold_at_precision(0.85) against the
             model's own reference-free label (the Q3b/SessN3 nested rule applied at the top level). The reference is not
             read to choose it.

Checks (scoring only; the reference is read here and nowhere else):
  R1 Q3c reproduction: nested_train + score_matched at precision 0.825 must give Q3c_results.json's
     reffree_uniform recall exactly.
  R2 the blind threshold's held-out operating point against the reference (per-fold nested thresholds, as SessN3).
Outputs: risk_model_v1.joblib, risk_model_v1.json (threshold, features, hashes, checks).
Run from a checkout that contains phase/q3 and phase/h1 (the integration branch)."""
import hashlib
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

O = Path(__file__).resolve().parent; R = O.parents[2]
sys.path.insert(0, str(R / "phase/h1")); sys.path.insert(0, str(R / "phase/q3"))
import q3_common as q3c  # noqa: E402
import q3c_deploy as Q  # noqa: E402
from q3_part2 import FEATURES, threshold_at_precision  # noqa: E402
from q3b_deploy import nested_train  # noqa: E402

t0 = time.process_time()
state = q3c.build_full_state()
d = np.load(R / "phase/q3/Q3_consensus.npz")
cons = {(min(int(a), int(b)), max(int(a), int(b))): int(l) for a, b, l in zip(d["row_a"], d["row_b"], d["consensus_label"])}
dii = {}
for e in state["E"]:
    if e["d_ii"] is not None:
        pa, pb = int(e["a"]), int(e["b"]); dii[(min(pa, pb), max(pa, pb))] = int(e["d_ii"] != 0)
lab_u, s_u, _ = Q.solve_consensus_labels(state, Q.uniform_weight, "uniform")
lab_sf, _, _ = Q.solve_consensus_labels(state, Q.make_support_fraction_weight(), "support_fraction")
rows = Q.load_common()
elig = Q.attach_labels_and_folds(rows, dict(consensus=cons, measurement_ii=dii, reffree_uniform=lab_u, reffree_supportfrac=lab_sf))
X = np.array([[r[c] for c in FEATURES] for r in elig], float)
active = [i for i in range(len(FEATURES)) if np.isfinite(X[:, i]).any()]
y_rf = np.array([r["reffree_uniform"] for r in elig]); fold = np.array([r["fold"] for r in elig])
y_ref = np.array([r["label"] for r in elig]); blocks = np.array([r["patch_a"] for r in elig])

# R1: Q3c reproduction
proba, fold_thr = nested_train(X, y_rf, fold, active)
m = Q.score_matched(proba, fold, y_ref, None, blocks, 0.825)
q3c_res = json.load(open(R / "phase/q3/Q3c_results.json"))["matched"]["reffree_uniform"]["0.825"]
r1 = dict(recall=m["recall"], q3c_recall=q3c_res["recall"], identical=m["recall"] == q3c_res["recall"])
print("R1", r1, flush=True)

# R2: nested (per outer fold) blind operating point, scored against the reference
call = np.zeros(len(y_ref), bool)
for f, t in fold_thr.items():
    call[fold == f] = proba[fold == f] >= t
tp = int((call & (y_ref == 1)).sum())
r2 = dict(fold_thresholds={str(k): v for k, v in fold_thr.items()}, called=int(call.sum()), positives=int(y_ref.sum()),
          precision=tp / max(int(call.sum()), 1), recall=tp / max(int(y_ref.sum()), 1))
print("R2", r2, flush=True)

# deployable threshold: top-level out-of-fold probabilities on the reference-free label
oof = np.full(len(y_rf), np.nan)
for f in range(4):
    tr, te = fold != f, fold == f
    oof[te] = HistGradientBoostingClassifier(class_weight="balanced", random_state=8).fit(X[tr][:, active], y_rf[tr]).predict_proba(X[te][:, active])[:, 1]
thr = threshold_at_precision(y_rf, oof, 0.85)
oof_call = oof >= thr; tp = int((oof_call & (y_ref == 1)).sum())
r3 = dict(threshold=thr, called=int(oof_call.sum()), precision_vs_reference=tp / max(int(oof_call.sum()), 1),
          recall_vs_reference=tp / max(int(y_ref.sum()), 1),
          precision_vs_own_label=float((oof_call & (y_rf == 1)).sum() / max(int(oof_call.sum()), 1)))
print("threshold", r3, flush=True)

clf = HistGradientBoostingClassifier(class_weight="balanced", random_state=8).fit(X[:, active], y_rf)
feats = [FEATURES[i] for i in active]
joblib.dump(dict(model=clf, active_features=feats, schema_features=FEATURES, threshold=thr, version="v1"), O / "risk_model_v1.joblib")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
meta = dict(version="v1", model="HistGradientBoostingClassifier(class_weight='balanced', random_state=8)",
            label="Q3c reference-free uniform consensus: round(k_b - k_a) != 0; handedness chosen s=%d" % s_u,
            active_features=feats, n_train=int(len(y_rf)), train_positives=int(y_rf.sum()),
            blind_threshold=thr, threshold_rule="threshold_at_precision(oof, own reference-free label, 0.85), 4 patch-z folds",
            checks=dict(R1_q3c_reproduction=r1, R2_nested_heldout_vs_reference=r2, R3_blind_threshold_oof=r3),
            sklearn=sklearn.__version__, numpy=np.__version__,
            inputs={p: sha(R / p) for p in ("phase/x8/pairs_dataset.csv", "phase/x6/x6b_pairs.csv", "phase/x6/x6b_points.npz",
                                           "phase/x1/patches.csv", "phase/q3/q3c_deploy.py", "phase/q3/q3_common.py",
                                           "phase/q3/Q3_consensus.npz", "phase/data_small/x4test/complete_surface_200um.npz")},
            model_sha256=sha(O / "risk_model_v1.joblib"), cpu_s=round(time.process_time() - t0, 1))
json.dump(meta, open(O / "risk_model_v1.json", "w"), indent=1, default=float)
print("done", meta["cpu_s"])
