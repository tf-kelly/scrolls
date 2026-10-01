#!/usr/bin/env python3
"""P1FIX step 3: per page, agreement of the page with the index before and after the re-solve, from each page's saved
matching (page<k>_key.npz from p1fix_page_key.py: page node -> patch, along-sheet unwrapped angle). Key per node =
round(k + s * (thN - Theta') / 2 pi) with k, thN from the given wrap index; agreement = share of matched nodes on the
modal key; minority area at the grid's cell size (smoothing as in p1fix_page_key.py). Also: patches whose k changed
between the two indexes (up to one constant per component).
Usage: p1fix_rescore.py KEY_DIR BEFORE_WRAP_CSV AFTER_WRAP_CSV OUT.json [--s 1] [--step 4]"""
import json, sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

TWO_PI = 2 * np.pi; VOX_CM2 = (7.91e-4) ** 2


def score(K, wi, s, step):
    ok, pid, Th, ii, jj = K["matched"], K["patch"], K["theta_unwrapped"], K["ii"], K["jj"]
    k = wi.k_q3c.reindex(pid[ok]).values; th = wi.thN.reindex(pid[ok]).values
    key = np.rint(k + s * (th - Th[ok]) / TWO_PI).astype(np.int64)
    vals, cnt = np.unique(key, return_counts=True); modal = int(vals[np.argmax(cnt)])
    H, W = ii.max() + 1, jj.max() + 1; V = np.zeros((H, W)); I = np.zeros((H, W))
    V[ii[ok], jj[ok]] = 1; I[ii[ok], jj[ok]] = key == modal; win = max(1, int(round(60 / (4 * step))))
    fr = ndimage.uniform_filter(I, win) / np.maximum(ndimage.uniform_filter(V, win), 1e-9)
    cell = (4 * step) ** 2 * VOX_CM2
    return dict(modal_key=modal, modal_share=round(float(cnt.max() / cnt.sum()), 4),
                minority_area_raw_cm2=round(float((cnt.sum() - cnt.max()) * cell), 2),
                minority_area_smoothed_cm2=round(float((fr[ii[ok], jj[ok]] <= 0.5).sum() * cell), 2))


def main():
    a = sys.argv[1:]; kd, bf, af, out = Path(a[0]), a[1], a[2], a[3]
    s = int(a[a.index("--s") + 1]) if "--s" in a else 1; step = int(a[a.index("--step") + 1]) if "--step" in a else 4
    B = pd.read_csv(bf).set_index("patch"); A = pd.read_csv(af).set_index("patch")
    pages = {}
    for f in sorted(kd.glob("page*_key.npz")):
        p = int(f.stem[4:].split("_")[0]); K = np.load(f)
        pages[p] = dict(before=score(K, B, s, step), after=score(K, A, s, step))
        pages[p]["change_modal_share_points"] = round(100 * (pages[p]["after"]["modal_share"] - pages[p]["before"]["modal_share"]), 2)
    com = B.index.intersection(A.index); d = (A.k_q3c[com] - B.k_q3c[com]); comp = B.component[com]
    off = d.groupby(comp).agg(lambda x: x.mode().iloc[0]); changed = int((d != off.reindex(comp).values).sum())
    res = dict(rule=__doc__.split("Usage")[0].strip(), before=bf, after=af, pages=pages, patches_compared=int(len(com)),
               patches_k_changed_up_to_component_constant=changed)
    json.dump(res, open(out, "w"), indent=1)
    print("page  before_share  after_share  change_pts  minority_cm2 before->after")
    for p, r in sorted(pages.items()):
        print(p, r["before"]["modal_share"], r["after"]["modal_share"], r["change_modal_share_points"],
              r["before"]["minority_area_raw_cm2"], "->", r["after"]["minority_area_raw_cm2"])
    print("patches with k changed (up to a component constant):", changed, "of", len(com))


if __name__ == "__main__":
    main()
