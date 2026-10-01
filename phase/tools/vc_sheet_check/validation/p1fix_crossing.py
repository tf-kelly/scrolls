#!/usr/bin/env python3
"""P1FIX step 2 (P1FIX_PROTOCOL.md): boundary, sides, crossing constraints and their thresholds, for one page.

Boundary nodes: matched page nodes whose smoothed on-modal flag differs from a 4-neighbour's. Side M / side m: patches
matched by on-modal / off-modal page nodes within 50 vox of a boundary node; a patch on both sides is "split".
Crossing constraints: SessA-12 solve edges (a, b) with a on M and b on m (either order), or with a split patch at one end
and any side patch at the other: listed with d_i, d_ii (at 134 um), Stevens flag, witness
n_testable / agreement / verdict, the page's key relation, and the SessA-15 unsatisfied terms.
Below threshold: verdict 'ambiguous' (agreement < 0.8) or 'untestable' (n_testable = 0).
Usage: p1fix_crossing.py KEY_NPZ SOLVE_EDGES_JSON UNSATISFIED_CSV WRAP_INDEX_CSV OUT.json"""
import json, sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

SP_UM = 134.0; STEVENS = 0.59


def main():
    kf, sef, unf, wif, out = sys.argv[1:6]
    K = np.load(kf); ii, jj, P, pid, key, onm, ok = K["ii"], K["jj"], K["xyz"], K["patch"], K["key"], K["on_modal"], K["matched"]
    H, W = ii.max() + 1, jj.max() + 1
    idx = -np.ones((H, W), np.int64); idx[ii, jj] = np.arange(len(ii))
    bnd = np.zeros(len(ii), bool)
    for di, dj in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        i2, j2 = ii + di, jj + dj; m = (i2 >= 0) & (i2 < H) & (j2 >= 0) & (j2 < W)
        nb = np.full(len(ii), -1); nb[m] = idx[i2[m], j2[m]]; mm = (nb >= 0) & ok & ok[np.maximum(nb, 0)]
        bnd[mm] |= onm[mm] != onm[nb[mm]]
    near = np.zeros(len(ii), bool)
    if bnd.any():
        d, _ = cKDTree(P[bnd]).query(P, k=1, distance_upper_bound=50); near = np.isfinite(d)
    sel = near & ok & (pid >= 0)
    M = set(pid[sel & onm].tolist()); m_ = set(pid[sel & ~onm].tolist()); split = M & m_; Mo, mo = M - split, m_ - split
    E = json.load(open(sef))["edges"]; un = pd.read_csv(unf)
    unk = {}
    for r in un.itertuples(index=False):
        unk.setdefault(tuple(sorted((int(r.patch_a), int(r.patch_b)))), []).append(r.type)
    wi = pd.read_csv(wif).set_index("patch")
    side = {p: "M" for p in Mo}; side.update({p: "m" for p in mo}); side.update({p: "split" for p in split})
    rows = []
    for e in E:
        a, b = int(e["a"]), int(e["b"])
        sa, sb = side.get(a), side.get(b)
        if sa is None or sb is None: continue
        if not ({sa, sb} == {"M", "m"} or "split" in (sa, sb)): continue
        d_ii = None if e.get("sep_ii_um") is None else int(round(e["sep_ii_um"] / SP_UM))
        below = e.get("verdict") in ("ambiguous", "untestable") or int(e.get("n_testable") or 0) == 0
        rows.append(dict(a=a, b=b, side_a=sa, side_b=sb, d_i=e.get("d_i"), d_ii=d_ii, stevens=bool(e["msep_um"] > STEVENS * SP_UM),
                         verdict=e.get("verdict"), n_testable=int(e.get("n_testable") or 0), agreement=e.get("agreement"),
                         k_a=int(wi.k_q3c.get(a, -999)), k_b=int(wi.k_q3c.get(b, -999)),
                         unsatisfied_terms=unk.get(tuple(sorted((a, b))), []), below_threshold=bool(below)))
    res = dict(boundary_nodes=int(bnd.sum()), near_nodes=int(sel.sum()), side_M=sorted(Mo), side_m=sorted(mo), split=sorted(split),
               crossing_constraints=len(rows), below_threshold=sum(r["below_threshold"] for r in rows),
               with_unsatisfied_terms=sum(bool(r["unsatisfied_terms"]) for r in rows), constraints=rows)
    json.dump(res, open(out, "w"), indent=1, default=float)
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    main()
