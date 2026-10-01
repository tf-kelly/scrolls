"""F1b score (PREREG_F1B.md): responses_f1b.json (committed first, 25537407) against unsealed_f1b/key.json.
  score_f1b.py -> score_f1b.json"""
import json, math
from collections import Counter, defaultdict
R = json.load(open("responses_f1b.json")); K = {it["id"]: it for it in json.load(open("unsealed_f1b/key.json"))["items"]}


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(c - h, 0), 3), round(min(c + h, 1), 3)]


by = defaultdict(Counter); rows = []
for a in R["answers"]:
    it = K[a["item"]]; by[it["class"]][a["answer"]] += 1
    rows.append({"item": a["item"], "class": it["class"], "patches": it["patches"], "w_v": it["w_v"], "xyz": it["xyz"], "cov": it["cov"], "answer": a["answer"], "note": a.get("note", "")})
out = {"groups": {g: {"n": sum(c.values()), **dict(c), "different_rate": round(c["different"] / sum(c.values()), 3), "different_wilson95": wilson(c["different"], sum(c.values()))} for g, c in by.items()}}
tc, sw = by["TC"], by["SW"]
out["rule"] = {"TC_different": f"{tc['different']}/20", "SW_different": f"{sw['different']}/10", "holds": bool(tc["different"] >= 14 and sw["different"] <= 2)}
out["prediction_TC_8_15"] = 8 <= tc["different"] <= 15; out["prediction_SW_0_2"] = sw["different"] <= 2
# fisher exact one-sided: TC different rate > SW different rate
from math import comb
a_, b_, c_, d_ = tc["different"], 20 - tc["different"], sw["different"], 10 - sw["different"]; n1, n2, m = 20, 10, a_ + c_
p = sum(comb(n1, x) * comb(n2, m - x) for x in range(a_, min(n1, m) + 1)) / comb(30, m); out["fisher_one_sided_p_TC_gt_SW"] = round(p, 4)
out["items"] = rows
json.dump(out, open("score_f1b.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "items"}, indent=1))
for r in rows: print(r["class"], r["w_v"], [int(x) for x in r["xyz"]], r["answer"], r["note"])
