"""2x2: Stevens bad/good x our flagged/unflagged over the index patches (PREREG_bad_vs_flags.md). Stdlib only.
Usage: python table2x2.py GOOD_IDS BAD_IDS WRAP_INDEX_CSV FLAGS_CSV SOLVE_EDGES_JSON OUT_JSON"""
import csv, json, sys
from collections import Counter
G, B, W, F, E, OUT = sys.argv[1:7]
good, bad = set(open(G).read().split()), set(open(B).read().split())
idx = {r["patch"] for r in csv.DictReader(open(W))}
flag, rows, types = set(), 0, Counter()
for r in csv.DictReader(open(F)):
    flag |= {r["patch_a"], r["patch_b"]}; rows += 1; types[r["type"]] += 1
deg = Counter()
for e in json.load(open(E))["edges"]:
    deg[str(e["a"])] += 1; deg[str(e["b"])] += 1
def cell(s): return dict(n=len(s), flagged=len(s & flag), unflagged=len(s - flag), rate=len(s & flag) / len(s) if s else None)
out = dict(flag_rows=rows, flag_row_types=dict(types), flagged_patches=len(flag), index_patches=len(idx),
           bad=cell(bad & idx), good=cell(good & idx), not_in_index=dict(good=len(good - idx), bad=len(bad - idx)),
           flags_outside_index=len(flag - idx))
out["prediction_holds"] = out["bad"]["rate"] >= 0.40 and out["good"]["rate"] < 0.10
# join-count quartiles (reporting only)
ds = sorted(deg[p] for p in idx); q = [ds[len(ds) * k // 4] for k in (1, 2, 3)]
def qi(p): d = deg[p]; return sum(d >= t for t in q)
out["join_quartile_edges"] = q
out["by_join_quartile"] = {str(k): dict(bad=cell({p for p in bad & idx if qi(p) == k}), good=cell({p for p in good & idx if qi(p) == k})) for k in range(4)}
out["median_joins"] = dict(bad=sorted(deg[p] for p in bad & idx)[len(bad & idx) // 2], good=sorted(deg[p] for p in good & idx)[len(good & idx) // 2])
json.dump(out, open(OUT, "w"), indent=1)
print(json.dumps({k: out[k] for k in ("flagged_patches", "bad", "good", "not_in_index", "prediction_holds", "median_joins")}, indent=0))
for k, v in out["by_join_quartile"].items(): print("Q", k, "bad", v["bad"]["flagged"], "/", v["bad"]["n"], "good", v["good"]["flagged"], "/", v["good"]["n"])
