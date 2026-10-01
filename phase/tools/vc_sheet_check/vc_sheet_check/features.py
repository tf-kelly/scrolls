"""Per-pair witness features for the frozen risk model (contract §3), recomputed from a field.

Definitions are phase/x8/build_dataset.py's, fed by the switchwitness enumeration and
witness (phase/x3/switchwitness/core.py pairs()/witness()/verdicts(), vendored unmodified):
  median_count, agreement, n_testable   verdicts() over the pair's snapped crossing counts
  sep_um            median normal separation over the pair's evaluated points x 7.91
                    (phase/x4/x4.py merge(): sep_um = median(W["sep"]) * UM0)
  support_fraction  n_testable / (xy bbox overlap / 16)   (4-voxel grid step)
  stevens_dist_vox  pipeline9's badpatchscores distance for the pair, NaN if absent
  area_a, area_b    patch point counts n;  z_um = mean patch centroid z x 7.91
One difference from the training data is deliberate and reported: the field here has a
fixed 80 um period (the brief). The slab-2 field behind the training features had an
estimated period of 118.67 um (phase/x3/results/slab2/field.json).
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

VOX_UM = 7.91
FEATURES = ["sep_um", "median_count", "agreement", "n_testable", "support_fraction", "stevens_dist_vox",
            "area_a", "area_b", "z_um"]


def enumerate_pairs(rows, G, cache):
    """switchwitness pairs(): overlapping patch pairs and their matched point pairs."""
    from ._vendor import switchwitness_core as SW
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    ids = [int(r["id"]) for r in rows]
    grids = [G[i].astype(np.float32) for i in ids]
    P = SW.pairs(rows, grids, cache)
    meta = [(ids[i], ids[j]) for i, j in P["meta"]]
    return P, meta


def points_bbox(P, halo):
    pts = np.concatenate([P["PA"], P["PB"]])
    return pts.min(0) - halo, pts.max(0) + halo          # x, y, z


def witness_stable(P, fld, per0_l0):
    """switchwitness witness()'s definitions (normal separation > 1 voxel; snap both ends; signed crossing count between
    snapped points) with Field.count called per per-pair sample-count group, so each pair's count depends only on
    itself (SessA-4's count_dense rule). witness() itself calls Field.count once over all pairs, which is batch-dependent."""
    from .check import count_dense
    PA, PB, PI = P["PA"], P["PB"], P["PI"]
    sep = np.abs(np.sum((PB - PA) * fld.normal((PA + PB) / 2), 1)); ia = np.where(sep > 1)[0]
    pa, pb = PA[ia], PB[ia]; sa, _ = fld.snap(pa, tmax=per0_l0); sb, _ = fld.snap(pb, tmax=per0_l0)
    S = np.concatenate([sa, sb]); n = len(ia)
    c_, o_ = count_dense(fld, S, np.arange(n), np.arange(n, 2 * n))
    cs = np.full(n, np.nan); cs[o_] = np.rint(c_[o_])
    return dict(ia=ia, cs=cs, pi=PI[ia], sep=sep[ia])


def witness_features(P, meta, rows, fld, per0_l0, cache, stevens=None, W=None):
    from ._vendor import switchwitness_core as SW
    W = SW.witness(P, fld, per0_l0, Path(cache)) if W is None else W
    V, MED, AG, NT = SW.verdicts(W, len(meta))
    tab = {int(r["id"]): r for r in rows}
    o = np.argsort(W["pi"], kind="stable"); cut = np.searchsorted(W["pi"][o], np.arange(len(meta) + 1))
    out = []
    for q, (a, b) in enumerate(meta):
        sel = o[cut[q]:cut[q + 1]]
        ra, rb = tab[a], tab[b]
        ox = max(0.0, min(float(ra["xmax"]), float(rb["xmax"])) - max(float(ra["xmin"]), float(rb["xmin"])))
        oy = max(0.0, min(float(ra["ymax"]), float(rb["ymax"])) - max(float(ra["ymin"]), float(rb["ymin"])))
        grid = ox * oy / 16.0
        k = (min(a, b), max(a, b))
        out.append(dict(patch_a=k[0], patch_b=k[1], verdict=str(V[q]),
                        sep_um=float(np.median(W["sep"][sel])) * VOX_UM if len(sel) else np.nan,
                        median_count=float(MED[q]), agreement=float(AG[q]), n_testable=int(NT[q]),
                        support_fraction=NT[q] / grid if grid > 0 else np.nan,
                        stevens_dist_vox=(stevens or {}).get(k, np.nan),
                        area_a=int(tab[k[0]]["n"]), area_b=int(tab[k[1]]["n"]),
                        z_um=0.5 * (float(ra["cz"]) + float(rb["cz"])) * VOX_UM, n_eval=int(len(sel))))
    return out, W


def load_stevens(path):
    d = {}
    if path and Path(path).exists():
        for row in csv.reader(open(path)):
            try:
                a, b, dist = int(row[0]), int(row[1]), float(row[2])
            except ValueError:
                continue
            d[(min(a, b), max(a, b))] = dist
    return d


def score(feats, model_path):
    import joblib
    mdl = joblib.load(model_path)
    X = np.array([[float(f[c]) if f[c] not in ("", None) else np.nan for c in mdl["active_features"]] for f in feats], float)
    p = mdl["model"].predict_proba(X)[:, 1] if len(X) else np.zeros(0)
    return p, float(mdl["threshold"]), list(mdl["active_features"])
