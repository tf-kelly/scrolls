#!/usr/bin/env python3
"""Page and switch metrics for the integration contract (phase/tools/CONTRACT.md §5).

Independent re-implementation of the measures defined in phase/notes/C1.md (P1c, P1e, P1f) and of the
precision/recall block bootstrap in phase/writeup/w3_stats.py / w4_stats.py. Nothing here imports the stage scripts;
phase/tools/test_metrics.py checks this module against ledger rows SessN8-04 and SessN4-01.

Units: patch/page areas in mm² (bbox-sum as P1c unless points are given), coordinates in scan voxels (7.91 µm).

Measures (a page is a union-find component of the kept joins whose area is >= 1 cm²):
  M1  component purity: page area in pages that retain no cross-turn join / total page area.
  M2  area purity. Two versions:
        m2_patch  (P1c): BFS sheet offset per patch over the page's joins (each join steps round(Δt)); the share of
                   page area at the page's area-weighted majority offset.
        m2_point  (contract amendment, headline): per point, the reference winding expressed in the page's own
                   unwrapped angle; the area-weighted share of each page's points on the page's majority reference
                   turn. Points with no reference within `max_ref_um` are excluded and counted.
  M3  cross-turn joins retained inside pages, per cm² of page area.
Cross-turn labellings: "per-patch layer" (|t_a - t_b| > 0.5, t = k_ref + θ/2π) or "X6 pairs" (x6b_pairs.csv truth
== adjacent; unresolved / missing joins excluded). Defect exclusion: P1f's reference test at the join midpoint.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np

VOX_UM = 7.91
TWO_PI = 2 * np.pi
PAGE_MIN_MM2 = 100.0
N_SECTORS, N_ZSLABS = 12, 4

# ----------------------------------------------------------------------------------------------- inputs

def bbox_area_mm2(patches_csv):
    """P1c's patch area: xy bounding-box area in mm² from phase/x1/patches.csv (xmin..ymax in voxels)."""
    out = {}
    for r in csv.DictReader(open(patches_csv)):
        dx = max(0.0, float(r["xmax"]) - float(r["xmin"])); dy = max(0.0, float(r["ymax"]) - float(r["ymin"]))
        out[int(r["id"])] = dx * dy * VOX_UM ** 2 / 1e6
    return out


def jkey(a, b):
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


# ----------------------------------------------------------------------------------------------- pages

def components(joins, nodes):
    """Union-find components over `nodes`; each component sorted, list order by smallest member."""
    par = {p: p for p in nodes}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for a, b in joins:
        if a in par and b in par:
            ra, rb = find(a), find(b)
            if ra != rb:
                par[max(ra, rb)] = min(ra, rb)
    groups = defaultdict(list)
    for p in nodes:
        groups[find(p)].append(p)
    return [sorted(g) for _, g in sorted(groups.items())]


def pages(joins, nodes, area, min_mm2=PAGE_MIN_MM2):
    return [c for c in components(joins, nodes) if sum(area[p] for p in c) >= min_mm2]


def page_joins(page, adj):
    s = set(page)
    return [(a, b) for a in page for b in adj[a] if b in s and a < b]


def adjacency(joins):
    adj = defaultdict(list)
    for a, b in joins:
        adj[a].append(b); adj[b].append(a)
    return adj


# ----------------------------------------------------------------------------------------------- labellings

def cross_per_patch_layer(t):
    """P1c: a join is cross-turn if both patches have a reference turn and they differ by more than 0.5."""
    return lambda k: (k[0] in t and k[1] in t and abs(t[k[0]] - t[k[1]]) > 0.5), (lambda k: False)


def cross_x6(x6_label, defect=None):
    """P1f: cross-turn iff X6 truth is 'adjacent'. Excluded: unresolved or no X6 row; with `defect`, also joins whose
    reference test is not 'ok' (M1-excl / M3-excl)."""
    def excl(k):
        lab = x6_label.get(k)
        if lab is None or lab == "unresolved":
            return True
        return defect is not None and defect.get(k, "ok") != "ok"
    return (lambda k: x6_label.get(k) == "adjacent"), excl


def load_x6_labels(x6b_pairs_csv):
    return {jkey(r["patch_a"], r["patch_b"]): r["truth"] for r in csv.DictReader(open(x6b_pairs_csv))}


# ----------------------------------------------------------------------------------------------- page records

def page_records(page_list, joins, area, is_cross, is_excluded=lambda k: False, t=None):
    """One record per page: area, cross joins, excluded count, and per patch (id, area, on_majority_offset|None).
    `t` (per-patch continuous reference turn) enables P1c's M2; without it M2 is not computed."""
    adj = adjacency(joins); recs = []
    for pl in page_list:
        pj = page_joins(pl, adj)
        ex = [k for k in pj if is_excluded(k)]
        cross = [k for k in pj if not is_excluded(k) and is_cross(k)]
        ok = {p: None for p in pl}
        if t is not None:
            s = set(pl); root = max(pl, key=lambda p: area[p]); off = {root: 0}; q = deque([root])
            while q:
                u = q.popleft()
                for v in sorted((w for w in adj[u] if w in s), key=lambda w: -area[w]):
                    if v in off:
                        continue
                    off[v] = off[u] + (int(round(t[v] - t[u])) if (u in t and v in t) else 0); q.append(v)
            cnt = Counter()
            for p in pl:
                if p in t:
                    cnt[off[p]] += area[p]
            mode = cnt.most_common(1)[0][0] if cnt else 0
            ok = {p: ((off[p] == mode) if p in t else None) for p in pl}
        recs.append(dict(area=sum(area[p] for p in pl), cross=cross, n_joins=len(pj), n_excluded=len(ex),
                         patches=[(p, area[p], ok[p]) for p in pl]))
    return recs


def summarize(recs, w=None):
    """M1, M2 (P1c, if computed), M3 and page area. `w`: per-patch bootstrap weight; a join carries the weight of
    its first (smaller-id) patch, exactly as P1c."""
    W = (lambda p: w[p]) if w is not None else (lambda p: 1.0)
    A = sum(a * W(p) for r in recs for p, a, _ in r["patches"])
    m1 = sum(a * W(p) for r in recs if not r["cross"] for p, a, _ in r["patches"])
    m2c = sum(a * W(p) for r in recs for p, a, ok in r["patches"] if ok is True)
    m2s = sum(a * W(p) for r in recs for p, a, ok in r["patches"] if ok is not None)
    cross = sum(W(a) for r in recs for a, _ in r["cross"])
    return dict(page_area_cm2=A / 100, M1=m1 / A if A else None, M2_patch=m2c / m2s if m2s else None,
                M3_per_cm2=cross / (A / 100) if A else None, cross_joins=cross,
                page_joins=sum(r["n_joins"] for r in recs), excluded_joins=sum(r["n_excluded"] for r in recs))


# ----------------------------------------------------------------------------------------------- M2 per point

def unwrap_page_theta(page, joins, theta_med):
    """Page-local unwrapped angle offset per patch: BFS over the page's joins from its first patch, adding the 2π
    multiple that makes neighbouring patch median angles continuous. Returns {patch: 2π·n}."""
    adj = adjacency(joins); s = set(page); root = page[0]; off = {root: 0.0}; q = deque([root])
    while q:
        u = q.popleft()
        for v in sorted(w for w in adj[u] if w in s):
            if v in off:
                continue
            d = theta_med[v] - theta_med[u]
            off[v] = off[u] - TWO_PI * np.round(d / TWO_PI); q.append(v)
    for p in page:
        off.setdefault(p, 0.0)
    return off


def m2_point_records(page_list, joins, pts_theta, pts_tref, pts_ok, pts_area_mm2=(4 * VOX_UM) ** 2 / 1e6):
    """Contract amendment M2 (headline). Per page and per point p of patch P:
        n(p) = round(t_ref(p) - (θ(p) + off_P) / 2π)
    where t_ref is the reference's continuous turn at p (turn count + θ/2π, as RefMesh.VT), θ(p) the point's angle
    about the axis and off_P the page-local unwrap offset of P. n is the reference winding in the page's own frame, so
    a page that legitimately spans the θ0 cut is not penalised. The page majority n is area-weighted over its points;
    points with pts_ok False (no reference within the limit) are excluded and counted.
    pts_* are dicts patch -> 1-D arrays. Returns per-page dicts (area_mm2, on_majority_mm2, excluded_mm2)."""
    out = []
    for pl in page_list:
        tmed = {p: float(np.angle(np.mean(np.exp(1j * pts_theta[p])))) % TWO_PI if len(pts_theta[p]) else 0.0 for p in pl}
        off = unwrap_page_theta(pl, joins, tmed)
        ns, ex = [], 0
        for p in pl:
            th = pts_theta[p]; ok = pts_ok[p]
            if not len(th):
                continue
            # unwrap each point's angle to lie within π of its patch median before applying the page offset
            thu = tmed[p] + (np.mod(th - tmed[p] + np.pi, TWO_PI) - np.pi) + off[p]
            n = np.round(pts_tref[p][ok] - thu[ok] / TWO_PI).astype(int)
            ns.append((p, n)); ex += int((~ok).sum())
        allv = np.concatenate([n for _, n in ns]) if ns else np.zeros(0, int)
        if len(allv):
            vals, cnt = np.unique(allv, return_counts=True); mode = vals[np.argmax(cnt)]
            on = int((allv == mode).sum())
        else:
            on = 0
        out.append(dict(patches=[p for p in pl], n_points=int(len(allv)), on_majority=on, excluded=ex,
                        per_patch_on={p: int((n == mode).sum()) if len(allv) else 0 for p, n in ns},
                        per_patch_n={p: int(len(n)) for p, n in ns}, area_per_point_mm2=pts_area_mm2))
    return out


def summarize_m2_point(recs, w=None):
    W = (lambda p: w[p]) if w is not None else (lambda p: 1.0)
    tot = sum(W(p) * r["per_patch_n"][p] for r in recs for p in r["per_patch_n"])
    on = sum(W(p) * r["per_patch_on"][p] for r in recs for p in r["per_patch_on"])
    ex = sum(r["excluded"] for r in recs)
    a = recs[0]["area_per_point_mm2"] if recs else 0.0
    return dict(M2_point=on / tot if tot else None, points=tot, excluded_points=ex, area_cm2=tot * a / 100)


# ----------------------------------------------------------------------------------------------- blocks, bootstrap

def sector(theta, n=N_SECTORS):
    return (np.mod(np.asarray(theta, float), TWO_PI) / TWO_PI * n).astype(int) % n


def zslab_fixed(z, z0, step, n=N_ZSLABS):
    """P1c: slabs of `step` voxels from z0, clipped to [0, n-1]."""
    return np.clip(((np.asarray(z, float) - z0) / step).astype(int), 0, n - 1)


def zslab_range(z, z0, z1, n=N_ZSLABS):
    """SessN2: n equal slabs over [z0, z1)."""
    return np.clip(((np.asarray(z, float) - z0) / (z1 - z0) * n).astype(int), 0, n - 1)


def block_id(sec, zs, n_z=N_ZSLABS):
    return np.asarray(sec) * n_z + np.asarray(zs)


def pair_theta(ta, tb):
    """SessN2: circular mean of the two patches' angles."""
    return np.angle(np.exp(1j * np.asarray(ta)) + np.exp(1j * np.asarray(tb)))


def block_weights(rng, n_blocks=N_SECTORS * N_ZSLABS):
    """One block-bootstrap draw: multiplicity of each block when n_blocks blocks are drawn with replacement."""
    return np.bincount(rng.integers(0, n_blocks, n_blocks), minlength=n_blocks).astype(float)


def ci95(v, nan=False):
    f = np.nanpercentile if nan else np.percentile
    return [float(f(v, 2.5)), float(f(v, 97.5))]


def page_bootstrap(recs, block_of, rng, n=1000, keys=("page_area_cm2", "M1", "M2_patch", "M3_per_cm2")):
    """P1c/P1f page intervals: per draw, each patch weighted by its block's multiplicity."""
    boots = defaultdict(list); nodes = [p for r in recs for p, _, _ in r["patches"]]
    for _ in range(n):
        cnt = block_weights(rng); w = {p: float(cnt[block_of[p]]) for p in nodes}
        s = summarize(recs, w)
        for k in keys:
            boots[k].append(np.nan if s[k] is None else s[k])
    return {k: ci95(v, nan=True) for k, v in boots.items()}


# ----------------------------------------------------------------------------------------------- switch metrics

def precision_recall(call, truth, w=None):
    call = np.asarray(call, bool); t = np.asarray(truth, int)
    w = np.ones(len(t)) if w is None else np.asarray(w, float)
    tp = (w * call * t).sum()
    return dict(n=int(len(t)), positives=int(t.sum()), called=int(call.sum()),
                precision=float(tp / max((w * call).sum(), 1e-12)),
                recall=float(tp / max((w * t).sum(), 1e-12)))


def threshold_at_precision(y, p, target=0.85):
    """Lowest score threshold whose precision (on the descending ranking) is >= target; 1.01 if none.
    Same rule as phase/q3/q3_part2.py and w3_stats.py."""
    y = np.asarray(y); p = np.asarray(p, float); m = np.isfinite(p)
    o = np.argsort(-p[m]); yy = y[m][o]; prec = np.cumsum(yy) / np.arange(1, len(yy) + 1); ok = np.where(prec >= target)[0]
    return float(p[m][o][ok.max()]) if len(ok) else 1.01


def recall_at_precision(y, p, target=0.85):
    thr = threshold_at_precision(y, p, target)
    return dict(threshold=thr, **precision_recall(np.asarray(p) >= thr, y))


def pr_block_bootstrap(call, truth, blocks, seed, n=1000):
    """SessN4: evaluation-only block bootstrap of precision and recall with calls held fixed."""
    call = np.asarray(call, bool); t = np.asarray(truth, int); blocks = np.asarray(blocks)
    rng = np.random.default_rng(seed); P, R = [], []
    for _ in range(n):
        w = block_weights(rng)[blocks]
        tp = (w * call * t).sum(); P.append(tp / max((w * call).sum(), 1e-12)); R.append(tp / max((w * t).sum(), 1e-12))
    return dict(precision_ci95=ci95(P), recall_ci95=ci95(R))


# ----------------------------------------------------------------------------------------------- defect test

def defect_at(m, tree, cols, pts, r60=60 / VOX_UM, r25=25 / VOX_UM, col_gap=100):
    """P1f reference-defect test at one join midpoint m (voxels). tree/pts: reference vertices; cols: their grid
    column (u index). 'displaced' if no vertex within 60 µm; 'duplicated' if two groups of vertices whose columns are
    > col_gap apart (different turns) both lie within 60 µm and come within 25 µm of each other; else 'ok'."""
    from scipy.spatial import cKDTree
    idx = tree.query_ball_point(m, r60)
    if not idx:
        return "displaced"
    idx = np.array(idx); c = cols[idx]; o = np.argsort(c); idx, c = idx[o], c[o]
    groups, cur = [], [idx[0]]
    for i in range(1, len(idx)):
        if c[i] - c[i - 1] > col_gap:
            groups.append(cur); cur = []
        cur.append(idx[i])
    groups.append(cur)
    for i in range(len(groups)):
        ti = cKDTree(pts[groups[i]])
        for j in range(i + 1, len(groups)):
            if ti.query(pts[groups[j]])[0].min() <= r25:
                return "duplicated"
    return "ok"


def join_midpoints(x6b_points_npz, x6_rows):
    """P1f: per X6 pair, the midpoint of its median-separation evaluated point pair. x6_rows: list of (a, b) in
    x6b_pairs.csv order. Returns {jkey: xyz}."""
    P6 = np.load(x6b_points_npz); pair = P6["pair"]; order = np.argsort(pair, kind="stable")
    cut = np.searchsorted(pair[order], np.arange(len(x6_rows) + 1)); out = {}
    for i, (a, b) in enumerate(x6_rows):
        ix = order[cut[i]:cut[i + 1]]
        if not len(ix):
            continue
        d = np.linalg.norm(P6["PA"][ix] - P6["PB"][ix], axis=1); j = ix[np.argsort(d)[len(d) // 2]]
        out[jkey(a, b)] = (P6["PA"][j] + P6["PB"][j]) / 2
    return out


# ----------------------------------------------------------------------------------------------- synthetic

def synthetic_checks():
    """Hand-built cases with known answers (P1c's and P1f's, plus the per-point M2 cut case)."""
    res = {}
    theta = {0: 5.8, 1: 6.1, 2: 0.1, 3: 0.6, 4: 1.1, 5: 1.6, 6: 2.0, 7: 2.4, 8: 6.1, 10: 3.0, 11: 3.1, 12: 3.2}
    kref = {0: 5, 1: 5, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6, 10: 5, 11: 5, 12: 5}
    t = {p: kref[p] + theta[p] / TWO_PI for p in kref}; area = {p: 100.0 for p in theta}
    J = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (1, 8), (10, 11), (11, 12)]
    pl = [[0, 1, 2, 3, 4, 5, 6, 7, 8], [10, 11, 12]]
    s = summarize(page_records(pl, J, area, *cross_per_patch_layer(t), t=t))
    res["p1c_page"] = abs(s["M1"] - 3 / 12) < 1e-12 and abs(s["M2_patch"] - 11 / 12) < 1e-12 and abs(s["M3_per_cm2"] - 1 / 12) < 1e-12
    lab = {(1, 2): "same-wrap", (2, 3): "adjacent", (3, 4): "unresolved"}
    s = summarize(page_records([[1, 2, 3, 4]], list(lab), {i: 100.0 for i in range(1, 5)}, *cross_x6(lab)))
    res["p1f_labels"] = s["M1"] == 0.0 and abs(s["M3_per_cm2"] - 0.25) < 1e-12 and s["page_joins"] == 3 and s["excluded_joins"] == 1
    # per-point M2: the same 1.3-turn page as points (10 per patch). Reference turn per point = kref + θ/2π, except
    # patch 8, which sits one turn out. Expected 80/90 on the majority turn; the θ0 crossing (patch 1 -> 2) must not
    # cost anything.
    pts_th, pts_t, pts_ok = {}, {}, {}
    for p in pl[0]:
        th = np.full(10, theta[p]) + np.linspace(-0.01, 0.01, 10)
        pts_th[p] = np.mod(th, TWO_PI); pts_t[p] = kref[p] + pts_th[p] / TWO_PI + (1 if p == 8 else 0); pts_ok[p] = np.ones(10, bool)
    r = summarize_m2_point(m2_point_records([pl[0]], J, pts_th, pts_t, pts_ok))
    res["m2_point_cut"] = abs(r["M2_point"] - 80 / 90) < 1e-12
    pts_ok[3] = np.r_[np.zeros(5, bool), np.ones(5, bool)]
    r = summarize_m2_point(m2_point_records([pl[0]], J, pts_th, pts_t, pts_ok))
    res["m2_point_excluded"] = r["excluded_points"] == 5 and abs(r["M2_point"] - 75 / 85) < 1e-12
    # defect test (P1f's four cases)
    from scipy.spatial import cKDTree
    g = np.arange(-20, 21) * 43 / VOX_UM / 4; X, Y = np.meshgrid(g, g); flat = np.column_stack([X.ravel(), Y.ravel(), np.zeros(X.size)])
    cases = {}
    for name, sheets in (("single", [(0.0, 0)]), ("copies_10um", [(0.0, 0), (10 / VOX_UM, 900)]),
                         ("contact_100um", [(0.0, 0), (100 / VOX_UM, 900)]), ("none", [(200 / VOX_UM, 0)])):
        P = np.concatenate([flat + [0, 0, z] for z, _ in sheets]); C = np.concatenate([np.full(len(flat), c) for _, c in sheets])
        cases[name] = defect_at(np.zeros(3), cKDTree(P), C.astype(float), P)
    res["defect"] = cases == {"single": "ok", "copies_10um": "duplicated", "contact_100um": "ok", "none": "displaced"}
    # recall at precision on a toy ranking
    y = np.array([1, 1, 0, 1, 0, 0]); p = np.array([.9, .8, .7, .6, .5, .4])
    r = recall_at_precision(y, p, 0.75)
    res["recall_at_precision"] = r["threshold"] == 0.6 and abs(r["recall"] - 1.0) < 1e-12 and abs(r["precision"] - 0.75) < 1e-12
    return res


if __name__ == "__main__":
    import json
    r = synthetic_checks(); print(json.dumps(r)); raise SystemExit(0 if all(r.values()) else 1)
