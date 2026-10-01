"""STAB scorer (phase/prereg/STAB.md, hash 2fd55d782ef2).
Usage: python stab_score.py RUNS_DIR WRAP_INDEX_V115 AREAS_JSON BAD_IDS GOOD_IDS PASS1_NPZ F1_KEY SCORE_F1B OUT_JSON"""
import csv, json, sys
from collections import Counter, defaultdict
import numpy as np
from scipy.stats import rankdata

RUNS, WI, AREAS, BAD, GOOD, P1, F1KEY, F1B, OUT = sys.argv[1:10]
full = {int(r["patch"]): int(r["k_q3c"]) for r in csv.DictReader(open(WI))}
area = {int(p): a for p, a in json.load(open(AREAS)).items()}
bad = {int(x) for x in open(BAD).read().split()}; good = {int(x) for x in open(GOOD).read().split()}


def load(mode):
    d = np.load(f"{RUNS}/{mode}.npz"); return d["nodes"], d["k"], d["component"], json.loads(str(d["meta"]))


def aligned_changed(nodes, k, comp):
    kf = np.array([full[int(p)] for p in nodes]); diff = k - kf; off = {}
    for c in np.unique(comp):
        off[c] = Counter(diff[comp == c].tolist()).most_common(1)[0][0]
    o = np.array([off[c] for c in comp]); return (k - o) != kf


out = {"prereg": "phase/prereg/STAB.md 2fd55d782ef2"}
# identity control
n, k, c, m = load("full"); ch = aligned_changed(n, k, c)
kf = np.array([full[int(p)] for p in n])
out["identity"] = dict(changed=int(ch.sum()), exact_equal_k=bool((k == kf).all()), meta=m)


def part_a(mode, kept_filter):
    n, k, c, m = load(mode); ch = aligned_changed(n, k, c)
    kept = np.array([kept_filter(int(p)) for p in n]); A = np.array([area[int(p)] for p in n])
    big = Counter(c[kept].tolist()).most_common(1)[0][0]
    return dict(kept_patches=int(kept.sum()), kept_area_cm2=float(A[kept].sum()), changed_patches=int((ch & kept).sum()),
                changed_area_cm2=float(A[ch & kept].sum()), share=float(A[ch & kept].sum() / A[kept].sum()),
                area_outside_largest_new_component_cm2=float(A[kept & (c != big)].sum()), n_components=int(len(np.unique(c))), meta=m)


out["a"] = part_a("a", lambda p: p in good)
out["a"]["hit"] = out["a"]["share"] < 0.05
out["null_a"] = part_a("null_a", lambda p: True)
# (b)
J = [load(f"jk{i}") for i in range(20)]
nodes = J[0][0]; pos = {int(p): i for i, p in enumerate(nodes)}
kfa = np.array([full[int(p)] for p in nodes])
stab_patch = np.zeros(len(nodes))
for n_, k_, c_, _ in J:
    assert (n_ == nodes).all()
    stab_patch += ~aligned_changed(n_, k_, c_)
stab_patch /= 20


def pair_stab(a, b):
    ia, ib = pos[a], pos[b]; s = 0; split = 0
    for n_, k_, c_, _ in J:
        if c_[ia] != c_[ib]: split += 1; continue
        s += (k_[ia] - k_[ib]) == (kfa[ia] - kfa[ib])
    return s / 20, split


# F1b candidate pool: build_f1b.py lines 36-47, unchanged
bins = np.load(P1)["bins"]
f1_pairs = {tuple(sorted(it["patches"])) for it in json.load(open(F1KEY))["items"] if it["class"] == "straddle"}
g = defaultdict(list)
for i_, b in enumerate(bins): g[(int(b[2]), int(b[3]))].append(i_)
cand = {1: {}, 0: {}}
for key, L in g.items():
    if len(L) < 2: continue
    A = bins[L]; o = np.argsort(A[:, 5]); A = A[o]; r = A[:, 5]
    for i in range(len(A)):
        for j in range(i + 1, np.searchsorted(r, r[i] + 4, side="right")):
            dw = abs(int(A[i, 1] - A[j, 1]))
            if A[i, 0] != A[j, 0] and dw in (0, 1) and np.linalg.norm(A[i, 6:9] - A[j, 6:9]) <= 30:
                pr = tuple(sorted((int(A[i, 0]), int(A[j, 0]))))
                if pr not in f1_pairs: cand[dw].setdefault(pr, True)
pool = list(cand[1]); out["pool"] = dict(n=len(pool), reproduces_46835=len(pool) == 46835)
ps = np.array([pair_stab(a, b)[0] for a, b in pool]); pidx = {p: i for i, p in enumerate(pool)}
pct = (rankdata(ps, method="average") - 0.5) / len(ps)
out["pool"].update(stability_quantiles={q: float(np.quantile(ps, q)) for q in (0.05, 0.1, 0.25, 0.5, 0.75)},
                   share_below_1=float((ps < 1).mean()), mean=float(ps.mean()))
items = json.load(open(F1B))["items"]


def group(answer):
    rows = []
    for it in items:
        if it["class"] != "TC" or it["answer"] != answer: continue
        pr = tuple(sorted(it["patches"])); s, split = pair_stab(*pr)
        inpool = pr in pidx; bq = bool(inpool and pct[pidx[pr]] <= 0.25)
        rows.append(dict(item=it["item"], patches=list(pr), w_v=it["w_v"], stability=s, split_runs=split, in_pool=inpool,
                         midrank_pct=float(pct[pidx[pr]]) if inpool else None, bottom_quartile=bq))
    return rows


out["b_same7"] = group("same"); out["b_diff12"] = group("different")
out["b"] = dict(count_same7_bottom=sum(r["bottom_quartile"] for r in out["b_same7"]),
                count_diff12_bottom=sum(r["bottom_quartile"] for r in out["b_diff12"]), expected_random_7=1.75)
out["b"]["hit"] = out["b"]["count_same7_bottom"] >= 4
zone = (kfa >= 26) & (kfa <= 30)
out["b_ii"] = dict(zone_patches=int(zone.sum()), zone_median=float(np.median(stab_patch[zone])),
                   zone_share_below_1=float((stab_patch[zone] < 1).mean()), other_median=float(np.median(stab_patch[~zone])),
                   other_share_below_1=float((stab_patch[~zone] < 1).mean()),
                   all_share_below_1=float((stab_patch < 1).mean()))
json.dump(out, open(OUT, "w"), indent=1, default=float)
print(json.dumps({k: out[k] for k in ("identity", "a", "null_a", "pool", "b", "b_ii")}, indent=1, default=float))
