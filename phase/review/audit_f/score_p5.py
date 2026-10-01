"""F2 page-5 deck score (BUILD_NOTES allocation, deck 3's H4 rule): responses_p5.json (committed first, 6b24e985)
against unsealed_p5/key.json (hash = keyhash_p5.txt).  score_p5.py -> score_p5.json"""
import json, math
from collections import Counter, defaultdict
R = json.load(open("responses_p5.json")); K = {it["id"]: it for it in json.load(open("unsealed_p5/key.json"))["items"]}


def wilson(k, n, z=1.96):
    if n == 0: return [None, None]
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(c - h, 0), 3), round(min(c + h, 1), 3)]


def ppf(p):                                           # inverse normal (Acklam)
    a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.383577518672690e2, -3.066479806614716e1, 2.506628277459239]
    b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1]
    c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783]
    d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416]
    if p < 0.02425: q = math.sqrt(-2 * math.log(p)); return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - 0.02425: q = math.sqrt(-2 * math.log(1 - p)); return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5; r = q * q; return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


by = defaultdict(Counter); rows = []
for a in R["answers"]:
    it = K[a["item"]]; g = it["group"]; by[g][a["answer"]] += 1
    rows.append({"item": a["item"], "group": g, "piece": it.get("piece"), "arc_frac": it.get("arc_frac"), "answer": a["answer"], "note": a.get("note", "")})
out = {"groups": {}}
for g, c in by.items():
    n = sum(c.values()); out["groups"][g] = {"n": n, **dict(c), "different_rate": round(c["different"] / n, 3), "different_wilson95": wilson(c["different"], n)}
b, cc = by["P5B"], by["P5C"]; nb, nc = sum(b.values()), sum(cc.values())
hr = (b["different"] + 0.5) / (nb + 1); fa = (cc["different"] + 0.5) / (nc + 1)
out["H4"] = {"P5B_different": f"{b['different']}/{nb}", "P5C_different": f"{cc['different']}/{nc}",
             "holds": bool(b["different"] / nb >= 2 / 3 and cc["different"] / nc <= 1 / 4), "d_prime_loglinear": round(ppf(hr) - ppf(fa), 2)}
out["items"] = rows
json.dump(out, open("score_p5.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "items"}, indent=1))
per = defaultdict(Counter)
for r in rows:
    if r["group"] == "P5B": per[r["piece"]][r["answer"]] += 1
print({k: dict(v) for k, v in sorted(per.items())})
for r in rows:
    if r["note"]: print(r)
