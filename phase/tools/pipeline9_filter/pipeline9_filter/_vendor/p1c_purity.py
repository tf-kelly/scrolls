#!/usr/bin/env python3
"""P1c: page purity on three measures for (i), (ii), (iii-new), (iii-rf) on the common join set, with 48-block spatial
intervals. M1 = area in page components with zero retained cross-turn joins; M2 = area at each page's majority sheet
offset (BFS over joins, each join stepping round(dt)); M3 = retained cross-turn joins per cm^2 of page area. P1b's
largest-piece purity is reported alongside. Definitions: phase/notes/C1.md, P1c (commit 12ce537). Synthetic first."""
import csv
import json
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import p1b_fair_table as FT  # noqa: E402

R = Path(__file__).resolve().parents[2]; OUT = Path(__file__).parent; TWO_PI = 2 * np.pi


def measures(pages, joins, area, t):
    """per page: dict(area, m1_pure, m2_correct_area, cross_joins, largest_piece_area, patches=[(p, a, m2ok)])"""
    adj = defaultdict(list)
    for a, b in joins:
        adj[a].append(b); adj[b].append(a)
    out = []
    for pl in pages:
        S = set(pl); A = sum(area[p] for p in pl)
        pj = [(a, b) for a in pl for b in adj[a] if b in S and a < b]
        cross = [(a, b) for a, b in pj if a in t and b in t and abs(t[a] - t[b]) > 0.5]
        # M2: BFS sheet offset from the largest patch, larger neighbours first
        root = max(pl, key=lambda p: area[p]); off = {root: 0}; q = deque([root])
        while q:
            u = q.popleft()
            for v in sorted((w for w in adj[u] if w in S), key=lambda w: -area[w]):
                if v in off:
                    continue
                step = int(round(t[v] - t[u])) if (u in t and v in t) else 0
                off[v] = off[u] + step; q.append(v)
        cnt = Counter()
        for p in pl:
            if p in t:
                cnt[off[p]] += area[p]
        mode = cnt.most_common(1)[0][0] if cnt else 0
        # P1b largest piece
        keep = [(a, b) for a, b in pj if (a, b) not in set(cross)]
        piece = max(FT.components(keep, pl), key=lambda c: sum(area[p] for p in c if p in t))
        pset = set(piece)
        out.append(dict(area=A, n_cross=len(cross), cross=cross,
                        patches=[(p, area[p], (off[p] == mode) if p in t else None, p in pset if p in t else None) for p in pl]))
    return out


def synthetic():
    """Page A (1.3 turns, 8 patches of 1 cm^2 in a chain crossing theta0) + patch 8 wrongly joined one turn out.
    Page B clean (3 patches). Expect: M1 = 3/12 (only B pure); M2 wrong = 1 cm^2 (patch 8); M3 = 1 join / 12 cm^2;
    P1b largest piece wrong = 1 cm^2. A clean multi-turn page must not be penalised by M2."""
    theta = {0: 5.8, 1: 6.1, 2: 0.1, 3: 0.6, 4: 1.1, 5: 1.6, 6: 2.0, 7: 2.4, 8: 6.1, 10: 3.0, 11: 3.1, 12: 3.2}
    kref = {0: 5, 1: 5, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6, 10: 5, 11: 5, 12: 5}
    t = {p: kref[p] + theta[p] / TWO_PI for p in kref}
    area = {p: 100.0 for p in theta}
    joins = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (1, 8), (10, 11), (11, 12)]
    pages = [[0, 1, 2, 3, 4, 5, 6, 7, 8], [10, 11, 12]]
    res = summarize(measures(pages, joins, area, t))
    ok = (abs(res["M1"] - 3 / 12) < 1e-9 and abs(res["M2"] - 11 / 12) < 1e-9 and abs(res["M3_per_cm2"] - 1 / 12) < 1e-9
          and abs(res["P1b_largest_piece"] - 11 / 12) < 1e-9)
    return dict(passed=bool(ok), got=res, expected=dict(M1=3 / 12, M2=11 / 12, M3_per_cm2=1 / 12, P1b_largest_piece=11 / 12))


def summarize(pm, w=None):
    """w: optional per-patch weight dict (block bootstrap); joins weighted by their first patch's weight."""
    W = (lambda p: w[p]) if w is not None else (lambda p: 1.0)
    A = sum(a * W(p) for pg in pm for p, a, _, _ in pg["patches"])
    m1 = sum(a * W(p) for pg in pm if pg["n_cross"] == 0 for p, a, _, _ in pg["patches"])
    m2c = sum(a * W(p) for pg in pm for p, a, ok, _ in pg["patches"] if ok is True)
    m2s = sum(a * W(p) for pg in pm for p, a, ok, _ in pg["patches"] if ok is not None)
    lpc = sum(a * W(p) for pg in pm for p, a, _, lp in pg["patches"] if lp is True)
    cross = sum(W(a_) for pg in pm for a_, _ in pg["cross"])
    return dict(page_area_cm2=A / 100, M1=m1 / A if A else None, M2=m2c / m2s if m2s else None,
                M3_per_cm2=cross / (A / 100) if A else None, P1b_largest_piece=lpc / m2s if m2s else None, cross_joins=cross)


def main():
    syn = synthetic(); print("synthetic", syn["passed"], syn["got"])
    if not syn["passed"]:
        sys.exit(1)
    VOX = 7.91
    pc = {int(r["id"]): r for r in csv.DictReader(open(R / "phase/x1/patches.csv"))}
    area = {p: max(0.0, float(r["xmax"]) - float(r["xmin"])) * max(0.0, float(r["ymax"]) - float(r["ymin"])) * VOX ** 2 / 1e6 for p, r in pc.items()}
    kref, theta = {}, {}
    for r in csv.DictReader(open(R / "phase/x7/X7_v9_patch_k.csv")):
        p = int(r["patch"]); theta[p] = float(r["theta_from_theta0"]) % TWO_PI
        if r["k_ref"] != "":
            kref[p] = int(r["k_ref"])
    t = {p: kref[p] + theta[p] / TWO_PI for p in kref}
    key = lambda a, b: (min(a, b), max(a, b))
    flip1 = {key(int(r[0]), int(r[1])) for r in csv.reader(open(R / "phase/x10/flip1_pairs.csv"))}
    U = sorted({key(int(r[0]), int(r[1])) for r in csv.reader(open(R / "phase/x5/rel.csv"))} - flip1)
    his_bad = {int(x) for x in open(R / "phase/x5/badpatches_b.csv").read().split() if x.strip()}
    v7 = {key(int(r["patch_a"]), int(r["patch_b"])): r for r in csv.DictReader(open(R / "phase/x10/x7_v7_edges.csv"))}

    def new_ok(k):
        v = v7.get(k)
        if v is None:
            return True
        if int(v["sync_implied"]) != 0:
            return False
        for c in ("d_i", "d_ii"):
            x = v.get(c)
            if x not in (None, "", "None"):
                return abs(int(v["sync_implied"]) - int(float(x))) == 0
        return True
    V = {"i_all": U, "ii_pipeline9_deletions": [k for k in U if k[0] not in his_bad and k[1] not in his_bad],
         "iii_new": [k for k in U if new_ok(k)], "iii_rf": [tuple(k) for k in json.load(open(OUT / "p1b_rf_joins.json"))["kept"]]}
    nodes = sorted({p for k in U for p in k})
    blk = {p: min(int(theta.get(p, 0.0) / TWO_PI * 12), 11) * 4 + min(max(int((float(pc[p]["cz"]) - 4096) / 192), 0), 3) for p in nodes}
    res = dict(synthetic=syn); rng = np.random.default_rng(0)
    for name, E in V.items():
        pages = [pl for pl in FT.components(E, nodes) if sum(area[p] for p in pl) >= 100.0]
        pm = measures(pages, E, area, t)
        pa = sorted((sum(area[p] for p in pl) / 100 for pl in pages), reverse=True)
        pt = summarize(pm)
        boots = defaultdict(list)
        for _ in range(1000):
            cnt = np.bincount(rng.integers(0, 48, 48), minlength=48); w = {p: float(cnt[blk[p]]) for p in nodes}
            s = summarize(pm, w)
            for k in ("page_area_cm2", "M1", "M2", "M3_per_cm2", "P1b_largest_piece"):
                boots[k].append(s[k])
        ci = {k: [round(float(np.nanpercentile(v, 2.5)), 4), round(float(np.nanpercentile(v, 97.5)), 4)] for k, v in boots.items()}
        res[name] = dict(n_joins=len(E), n_pages=len(pages), page_area_cm2_quartiles=[round(float(x), 2) for x in np.percentile(pa, [25, 50, 75])],
                         page_area_cm2_max=round(pa[0], 2), page_area_cm2_top3=[round(x, 2) for x in pa[:3]],
                         point={k: (round(v, 4) if isinstance(v, float) else v) for k, v in pt.items()}, ci95=ci,
                         pages_with_cross_joins=int(sum(pg["n_cross"] > 0 for pg in pm)))
        print(name, res[name]["n_pages"], res[name]["point"], res[name]["ci95"], flush=True)
    r, n = res["iii_rf"]["point"], res["ii_pipeline9_deletions"]["point"]
    res["prediction"] = dict(rf_beats_ii_M1=r["M1"] > n["M1"], rf_beats_ii_M2=r["M2"] > n["M2"], rf_beats_ii_M3=r["M3_per_cm2"] < n["M3_per_cm2"],
                             rf_pages_ge_2x_iii_new=res["iii_rf"]["n_pages"] >= 2 * res["iii_new"]["n_pages"])
    print(res["prediction"])
    json.dump(res, open(OUT / "p1c_purity.json", "w"), indent=1)


if __name__ == "__main__":
    main()
