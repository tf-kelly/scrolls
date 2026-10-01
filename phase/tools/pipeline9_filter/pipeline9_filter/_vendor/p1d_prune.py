#!/usr/bin/env python3
"""P1d: (1) mechanism of the M1 gap -- per variant, cross-turn joins, minority-side patches and area, bridging vs
loop-closing joins; (2) reference-free majority-turn pruning (Q3c continuous turn t_q = k_Q3c + thN/2pi, offsets
propagated over each page's joins, minority-offset patches dropped), then pages/M1/M2/M3 recomputed with 48-block
intervals. Applied to (ii) and (iii-rf). Definitions: phase/notes/C1.md, P1d (commit 23c8cc9). Synthetic first."""
import csv
import json
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import p1b_fair_table as FT  # noqa: E402
import p1c_purity as PU  # noqa: E402

R = Path(__file__).resolve().parents[2]; OUT = Path(__file__).parent; TWO_PI = 2 * np.pi


def offsets(pl, adj, tv, area):
    S = set(pl); root = max(pl, key=lambda p: area[p]); off = {root: 0}; q = deque([root])
    while q:
        u = q.popleft()
        for v in sorted((w for w in adj[u] if w in S), key=lambda w: -area[w]):
            if v in off:
                continue
            off[v] = off[u] + (int(round(tv[v] - tv[u])) if (u in tv and v in tv) else 0); q.append(v)
    return off


def prune(pages, joins, area, tq):
    adj = defaultdict(list)
    for a, b in joins:
        adj[a].append(b); adj[b].append(a)
    drop = set()
    for pl in pages:
        off = offsets(pl, adj, tq, area); cnt = Counter()
        for p in pl:
            if p in tq:
                cnt[off[p]] += area[p]
        if not cnt:
            continue
        mode = cnt.most_common(1)[0][0]
        drop |= {p for p in pl if p in tq and off[p] != mode}
    return drop


def mechanism(pm):
    n_cross = sum(pg["n_cross"] for pg in pm)
    minority = {p for pg in pm for p, a, ok, _ in pg["patches"] if ok is False}
    amin = sum(a for pg in pm for p, a, ok, _ in pg["patches"] if ok is False)
    bridging = [(a, b) for pg in pm for a, b in pg["cross"] if a in minority or b in minority]
    touched = {p for a, b in bridging for p in (a, b) if p in minority}
    return dict(cross_joins=n_cross, bridging=len(bridging), loop_closing=n_cross - len(bridging),
                minority_patches=len(minority), minority_patches_touched_by_cross_join=len(touched),
                minority_area_cm2=round(amin / 100, 3), minority_area_per_cross_join_cm2=round(amin / 100 / n_cross, 4) if n_cross else None,
                minority_area_per_bridging_join_cm2=round(amin / 100 / len(bridging), 4) if bridging else None)


def synthetic():
    """Page A: chain 0-1-2-3 on turn 5 plus patch 4 joined to 3 but on turn 6 (bridging, minority 1 cm^2), and a join
    3-5... Page also has patch 5 (turn 5) linked to 0 and to 2; the join 0-2 is labelled cross-turn by a noisy t (loop-closing).
    Our numbering tq agrees with the reference except patch 4 is numbered like the page (so pruning cannot see it) --
    and in page B patch 12 is on turn 6 by both, joined to 10 (pruning drops it)."""
    area = {p: 100.0 for p in (0, 1, 2, 3, 4, 10, 11, 12)}
    t = {0: 5.1, 1: 5.12, 2: 5.14, 3: 5.16, 4: 6.16, 10: 5.3, 11: 5.32, 12: 6.3}
    joins = [(0, 1), (1, 2), (2, 3), (3, 4), (10, 11), (10, 12)]
    t_noisy = dict(t); t_noisy[2] = 5.14   # clean
    pages = [[0, 1, 2, 3, 4], [10, 11, 12]]
    pm = PU.measures(pages, joins, area, t)
    mech = mechanism(pm)
    tq = dict(t); tq[4] = 5.16          # our numbering agrees with the wrong join at patch 4
    drop = prune(pages, joins, area, tq)
    ok = (mech["cross_joins"] == 2 and mech["bridging"] == 2 and mech["minority_patches"] == 2 and abs(mech["minority_area_per_cross_join_cm2"] - 1.0) < 1e-9
          and drop == {12})
    # loop-closing case: triangle 0-1-2 where the 0-2 join has |dt|>0.5 but BFS reaches 2 via 1 with step 0
    # root 0 (largest); 0-1-3 and 0-2-4 each step < 0.5 turn; the join 3-4 spans 1.2 turns but both ends are reached
    # by same-turn steps first, so it closes a loop and brings in no minority area
    t2 = {0: 5.0, 1: 5.3, 3: 5.6, 2: 4.7, 4: 4.4}
    a2 = {0: 500.0, 1: 100.0, 2: 100.0, 3: 100.0, 4: 100.0}
    pm2 = PU.measures([[0, 1, 2, 3, 4]], [(0, 1), (1, 3), (0, 2), (2, 4), (3, 4)], a2, t2)
    m2 = mechanism(pm2)
    ok2 = m2["cross_joins"] == 1 and m2["loop_closing"] == 1 and m2["minority_patches"] == 0
    return dict(passed=bool(ok and ok2), mech=mech, drop=sorted(drop), loop_case=m2)


def main():
    syn = synthetic(); print("synthetic", syn["passed"], syn)
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
    tq = {int(r["patch"]): int(r["k_q3c"]) + (float(r["thN"]) % TWO_PI) / TWO_PI for r in csv.DictReader(open(OUT / "p1b_q3c_k.csv"))}
    key = lambda a, b: (min(a, b), max(a, b))
    flip1 = {key(int(r[0]), int(r[1])) for r in csv.reader(open(R / "phase/x10/flip1_pairs.csv"))}
    U = sorted({key(int(r[0]), int(r[1])) for r in csv.reader(open(R / "phase/x5/rel.csv"))} - flip1)
    his_bad = {int(x) for x in open(R / "phase/x5/badpatches_b.csv").read().split() if x.strip()}
    V = {"i_all": U, "ii_pipeline9_deletions": [k for k in U if k[0] not in his_bad and k[1] not in his_bad],
         "iii_rf": [tuple(k) for k in json.load(open(OUT / "p1b_rf_joins.json"))["kept"]]}
    nodes = sorted({p for k in U for p in k})
    blk = {p: min(int(theta.get(p, 0.0) / TWO_PI * 12), 11) * 4 + min(max(int((float(pc[p]["cz"]) - 4096) / 192), 0), 3) for p in nodes}
    rng = np.random.default_rng(0)

    def evaluate(E, nodes_):
        pages = [pl for pl in FT.components(E, nodes_) if sum(area[p] for p in pl) >= 100.0]
        pm = PU.measures(pages, E, area, t)
        pt = PU.summarize(pm); boots = defaultdict(list)
        for _ in range(1000):
            cnt = np.bincount(rng.integers(0, 48, 48), minlength=48); w = {p: float(cnt[blk[p]]) for p in nodes_}
            s = PU.summarize(pm, w)
            for k in ("page_area_cm2", "M1", "M2", "M3_per_cm2"):
                boots[k].append(s[k])
        ci = {k: [round(float(np.nanpercentile(v, 2.5)), 4), round(float(np.nanpercentile(v, 97.5)), 4)] for k, v in boots.items()}
        return pages, pm, dict(n_pages=len(pages), point={k: (round(v, 4) if isinstance(v, float) else v) for k, v in pt.items()}, ci95=ci,
                               pages_with_cross_joins=int(sum(pg["n_cross"] > 0 for pg in pm)))
    res = dict(synthetic=syn)
    for name, E in V.items():
        pages, pm, ev = evaluate(E, nodes)
        ev["mechanism"] = mechanism(pm); res[name] = ev
        print(name, ev["n_pages"], ev["point"], ev["mechanism"], flush=True)
        if name == "i_all":
            continue
        drop = prune(pages, E, area, tq)
        E2 = [k for k in E if k[0] not in drop and k[1] not in drop]; n2 = [p for p in nodes if p not in drop]
        pages2, pm2, ev2 = evaluate(E2, n2)
        ev2["mechanism"] = mechanism(pm2)
        ev2["pruned_patches"] = len(drop); ev2["pruned_area_cm2"] = round(sum(area[p] for p in drop) / 100, 3)
        ev2["page_area_loss_frac"] = round(1 - ev2["point"]["page_area_cm2"] / ev["point"]["page_area_cm2"], 4)
        ev2["pruned_that_are_minority_by_reference"] = int(sum(1 for pg in pm for p, a, ok, _ in pg["patches"] if ok is False and p in drop))
        ev2["pruned_that_are_majority_by_reference"] = int(sum(1 for pg in pm for p, a, ok, _ in pg["patches"] if ok is True and p in drop))
        res[name + "_pruned"] = ev2
        print(name + "_pruned", ev2["n_pages"], ev2["point"], "dropped", len(drop), "loss", ev2["page_area_loss_frac"], flush=True)
    a, b = res["iii_rf_pruned"]["point"], res["ii_pipeline9_deletions_pruned"]["point"]
    mi, mr = res["ii_pipeline9_deletions"]["mechanism"], res["iii_rf"]["mechanism"]
    res["prediction"] = dict(
        ii_minority_area_per_join_ge_3x_rf=bool(mr["minority_area_per_cross_join_cm2"] and mi["minority_area_per_cross_join_cm2"] >= 3 * mr["minority_area_per_cross_join_cm2"]),
        pruned_rf_M1_ge_0p90_and_loss_lt_2pct=bool(a["M1"] >= 0.90 and res["iii_rf_pruned"]["page_area_loss_frac"] < 0.02),
        pruned_rf_beats_pruned_ii_all_three=bool(a["M1"] > b["M1"] and a["M2"] > b["M2"] and a["M3_per_cm2"] < b["M3_per_cm2"]))
    print(res["prediction"])
    json.dump(res, open(OUT / "p1d_prune.json", "w"), indent=1)


if __name__ == "__main__":
    main()
