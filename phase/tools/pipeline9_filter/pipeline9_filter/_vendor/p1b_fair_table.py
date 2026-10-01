#!/usr/bin/env python3
"""P1b (1): the fair page table. One join set (rel.csv minus flip=1-only), three variants, areas in cm^2 (bbox-sum),
48-block spatial bootstrap. Two purities: numbering-free (primary: page-consistent reference wrap vs the page's
area-weighted mode) and P1 Part A's B_page (k_ref - k_meas per-component offset; depends on v9's numbering).
A synthetic graph with a known answer is checked first. Definitions: phase/notes/C1.md, P1b (commit ad271b4)."""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
TWO_PI = 2 * np.pi


def components(edges, nodes):
    parent = {p: p for p in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    by = defaultdict(list)
    for p in nodes:
        by[find(p)].append(p)
    return list(by.values())


def page_rows(pages, area, kref, theta, s, kmeas=None, joins=()):
    """per patch in pages: (page, area, numbering-free status, B_page status, patch); 1 correct, 0 wrong, -1 unscored.
    Numbering-free: t = k_ref + s*theta/2pi is continuous along the (single, spiral) sheet, so a join between patches on
    the same turn has |dt| << 1 and a join onto the neighbouring turn has |dt| ~ 1. Inside each page, joins with |dt| > 0.5
    are removed; the largest-area piece is correct, the rest wrong. Multi-turn pages are handled (t keeps increasing)."""
    t = {p: kref[p] + s * theta[p] / TWO_PI for p in kref if p in theta}
    adj = defaultdict(list)
    for a, b in joins:
        adj[a].append(b); adj[b].append(a)
    rows = []
    for pi, pl in enumerate(pages):
        inpage = set(pl)
        keep = [(a, b) for a in pl for b in adj[a] if b in inpage and a < b and not (a in t and b in t and abs(t[a] - t[b]) > 0.5)]
        sub = components(keep, pl)
        main = max(sub, key=lambda c: sum(area[p] for p in c if p in t))
        mainset = set(main)
        off = None
        if kmeas is not None:
            sb = [p for p in pl if p in kref and p in kmeas]
            if sb:
                off = sorted(kref[p] - kmeas[p] for p in sb)[len(sb) // 2]
        for p in pl:
            nf = (1 if p in mainset else 0) if p in t else -1
            bp = int(kmeas[p] + off == kref[p]) if (off is not None and p in kref and p in kmeas) else -1
            rows.append((pi, area[p], nf, bp, p))
    return rows


def summarize(rows, col):
    a = np.array([r[1] for r in rows]); st = np.array([r[col] for r in rows])
    c, w = a[st == 1].sum(), a[st == 0].sum()
    return dict(page_area_cm2=round(a.sum() / 100, 2), correct_cm2=round(c / 100, 2), wrong_cm2=round(w / 100, 2), purity=round(c / (c + w), 4) if c + w else None)


def synthetic_check():
    """Page A: 8 patches of 1 cm^2 following the sheet 1.3 turns (theta 5.8 -> past theta0 -> 2.0; k_ref 5 then 6 past
    theta0; s=+1), all correctly joined in a chain, plus patch 8 joined to patch 1 but lying one turn out (k_ref 6 at
    theta 6.1: dt ~ 1) and patch 9 (correct geometry, v9 numbering error). Page B: 3 patches, correct.
    Expect numbering-free wrong = patch 8 only; B_page wrong = patch 9 (and 8)."""
    theta = {0: 5.8, 1: 6.1, 2: 0.1, 3: 0.6, 4: 1.1, 5: 1.6, 6: 2.0, 7: 2.4, 8: 6.1, 9: 2.8, 10: 3.0, 11: 3.1, 12: 3.2}
    kref = {0: 5, 1: 5, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6, 9: 6, 10: 5, 11: 5, 12: 5}
    kmeas = {0: 0, 1: 0, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 2, 10: 0, 11: 0, 12: 0}
    area = {i: 100.0 for i in theta}
    joins = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 9), (1, 8), (10, 11), (11, 12)]
    pages = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [10, 11, 12]]
    rows = page_rows(pages, area, kref, theta, +1, kmeas, joins)
    nf = {r[4]: r[2] for r in rows}; bp = {r[4]: r[3] for r in rows}
    ok = all(nf[i] == (0 if i == 8 else 1) for i in theta) and bp[9] == 0 and all(bp[i] == 1 for i in (0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12))
    return dict(passed=bool(ok), numbering_free=nf, b_page=bp,
                expected="numbering-free: only patch 8 (joined one turn out) wrong across a 1.3-turn page; B_page: 8 and 9 (numbering error) wrong")


def main():
    syn = synthetic_check(); print("synthetic", syn["passed"])
    if not syn["passed"]:
        json.dump(dict(synthetic=syn), open(OUT / "p1b_fair_table.json", "w"), indent=1); sys.exit(1)
    VOX = 7.91
    pc = {int(r["id"]): r for r in csv.DictReader(open(R / "phase/x1/patches.csv"))}
    area = {p: max(0.0, float(r["xmax"]) - float(r["xmin"])) * max(0.0, float(r["ymax"]) - float(r["ymin"])) * VOX ** 2 / 1e6 for p, r in pc.items()}
    kref, kmeas, theta = {}, {}, {}
    for r in csv.DictReader(open(R / "phase/x7/X7_v9_patch_k.csv")):
        p = int(r["patch"]); kmeas[p] = int(r["k_meas_cut"]); theta[p] = float(r["theta_from_theta0"]) % TWO_PI
        if r["k_ref"] != "":
            kref[p] = int(r["k_ref"])
    key = lambda a, b: (min(a, b), max(a, b))
    flip1 = {key(int(r[0]), int(r[1])) for r in csv.reader(open(R / "phase/x10/flip1_pairs.csv"))}
    U = sorted({key(int(r[0]), int(r[1])) for r in csv.reader(open(R / "phase/x5/rel.csv"))} - flip1)
    x6 = {key(int(r["patch_a"]), int(r["patch_b"])): r["truth"] for r in csv.DictReader(open(R / "phase/x6/x6b_pairs.csv"))}
    # cut sign s from same-wrap (X6) joins crossing theta0: k_ref(past) - k_ref(before)
    d = []
    for a, b in U:
        if x6.get((a, b)) == "same-wrap" and a in kref and b in kref and a in theta and b in theta and abs(theta[a] - theta[b]) > np.pi:
            lo, hi = (a, b) if theta[a] > theta[b] else (b, a)
            d.append(kref[hi] - kref[lo])
    cd = Counter(d); s = 1 if cd[1] >= cd[-1] else -1
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
    variants = {"i_all": U, "ii_pipeline9_deletions": [k for k in U if k[0] not in his_bad and k[1] not in his_bad],
                "iii_new": [k for k in U if new_ok(k)]}
    extra = OUT / "p1b_rf_joins.json"
    if extra.exists():                       # (iii-rf) from part (3), if already built
        variants["iii_rf"] = [tuple(k) for k in json.load(open(extra))["kept"]]
    nodes = sorted({p for k in U for p in k})
    # blocks: 12 sectors x 4 z-slabs
    blk = {p: min(int(theta.get(p, 0.0) / TWO_PI * 12), 11) * 4 + min(max(int((float(pc[p]["cz"]) - 4096) / 192), 0), 3) for p in nodes}
    res = dict(synthetic=syn, cut_sign=s, cut_sign_votes={str(k): v for k, v in cd.items()}, n_joins=len(U))
    rng = np.random.default_rng(0)
    for name, E in variants.items():
        pages = [pl for pl in components(E, nodes) if sum(area[p] for p in pl) >= 100.0]
        rows = page_rows(pages, area, kref, theta, s, kmeas, E)
        out = dict(n_joins=len(E), n_pages=len(pages), numbering_free=summarize(rows, 2), b_page_v9=summarize(rows, 3))
        a = np.array([r[1] for r in rows]); nf = np.array([r[2] for r in rows]); bp = np.array([r[3] for r in rows]); b = np.array([blk[r[4]] for r in rows])
        boots = defaultdict(list)
        for _ in range(1000):
            w = np.bincount(rng.integers(0, 48, 48), minlength=48)[b] * a
            for tag, st in (("nf", nf), ("bp", bp)):
                c, wr = w[st == 1].sum(), w[st == 0].sum()
                boots[tag + "_correct"].append(c / 100); boots[tag + "_wrong"].append(wr / 100); boots[tag + "_purity"].append(c / (c + wr))
            boots["page_area"].append(w.sum() / 100)
        out["block_ci95"] = {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] for k, v in boots.items()}
        res[name] = out
        print(name, out["n_pages"], out["numbering_free"], out["b_page_v9"])
    json.dump(res, open(OUT / "p1b_fair_table.json", "w"), indent=1)


if __name__ == "__main__":
    main()
