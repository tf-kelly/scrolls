"""S3 score (PREREG_S3.md): responses_s3.json (committed first, 4f9d8fe2) against unsealed/key.json. Rates per cell; no
pass/fail.  score_s3.py -> score_s3.json"""
import json, math
from collections import Counter, defaultdict
from math import comb
R = json.load(open("responses_s3.json")); K = {it["id"]: it for it in json.load(open("unsealed/key.json"))["items"]}


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(c - h, 0), 3), round(min(c + h, 1), 3)]


def fisher2(a, b, c, d):                              # two-sided Fisher exact, 2x2 [[a,b],[c,d]]
    n = a + b + c + d; r1, c1 = a + b, a + c
    pr = lambda x: comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    p0 = pr(a); return round(sum(pr(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if pr(x) <= p0 + 1e-12), 4)


by = defaultdict(Counter); rows = []
for a in R["answers"]:
    it = K[a["item"]]; by[it["cell"]][a["answer"]] += 1
    rows.append({"item": a["item"], "cell": it["cell"], "patch": it["patch"], "answer": a["answer"], "note": a.get("note", "")})
out = {"cells": {c: {"n": sum(v.values()), **dict(v), "yes_rate": round(v["yes"] / sum(v.values()), 3), "yes_wilson95": wilson(v["yes"], sum(v.values()))} for c, v in sorted(by.items())}}
ho, oo = by["HO"], by["OO"]
out["post_hoc"] = {"HO_vs_OO_no_fisher_two_sided": fisher2(ho["no"], 10 - ho["no"], oo["no"], 10 - oo["no"]),
                   "his_removed_no": f"{by['BB']['no'] + ho['no']}/20", "his_kept_no": f"{by['OO']['no'] + by['GG']['no']}/20",
                   "ours_bad_no": f"{by['BB']['no'] + oo['no']}/20", "ours_good_no": f"{ho['no'] + by['GG']['no']}/20"}
out["items"] = rows
json.dump(out, open("score_s3.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "items"}, indent=1))
