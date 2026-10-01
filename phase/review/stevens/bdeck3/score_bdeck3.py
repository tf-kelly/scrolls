"""Score blind deck 3 against PREREG.md.  score_bdeck3.py RESPONSES_JSON KEY_JSON OUT_JSON"""
import json, math, sys
from datetime import datetime
from statistics import NormalDist, median
resp, key, outp = sys.argv[1:4]
RA = json.load(open(resp))["answers"]; R = {a["item"]: a for a in RA}
K = {it["id"]: it for it in json.load(open(key))["items"]}
assert set(R) == set(K)
z = NormalDist().inv_cdf; ANS = ("same", "different", "cant")
ans = lambda i: R[i].get("answer") or "cant"


def wilson(k, n, zz=1.959964):
    if n == 0: return [None, None]
    p = k / n; d = 1 + zz * zz / n; c = (p + zz * zz / (2 * n)) / d; h = zz * math.sqrt(p * (1 - p) / n + zz * zz / (4 * n * n)) / d
    return [round(max(c - h, 0), 4), round(min(c + h, 1), 4)]


G = {g: [i for i in K if K[i]["group"] == g] for g in ("R02", "R5", "P1R", "ART", "DD", "DP")}
t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
out = {"groups": {}}
for g, ids in G.items():
    n = len(ids); cnt = {a: sum(ans(i) == a for i in ids) for a in ANS}
    out["groups"][g] = {"n": n, "counts": cnt, "rates": {a: round(cnt[a] / n, 4) if n else None for a in ANS},
                        "wilson95": {a: wilson(cnt[a], n) for a in ANS},
                        "median_seconds": round(median((t(R[i]["answered_at"]) - t(R[i]["shown_at"])).total_seconds() for i in ids), 2) if n else None}
dif = lambda ids: sum(ans(i) == "different" for i in ids)
ctrl = G["ART"] + G["DP"]
hit, fa = dif(G["R02"]) / len(G["R02"]), dif(ctrl) / len(ctrl)
Hc, Fc = (dif(G["R02"]) + 0.5) / (len(G["R02"]) + 1), (dif(ctrl) + 0.5) / (len(ctrl) + 1)
out["H4"] = {"different_rate_R02": round(hit, 4), "different_rate_ART_DP": round(fa, 4), "n_R02": len(G["R02"]), "n_ctrl": len(ctrl),
             "d_prime_loglinear": round(z(Hc) - z(Fc), 3), "holds": bool(hit >= 2 / 3 and fa <= 1 / 4)}
out["cant_tell_R02_gt_half"] = bool(out["groups"]["R02"]["counts"]["cant"] / len(G["R02"]) > 0.5)
out["H5_P1R_same_rate"] = out["groups"]["P1R"]["rates"]["same"]
out["median_seconds_all"] = round(median((t(a["answered_at"]) - t(a["shown_at"])).total_seconds() for a in RA), 2)
json.dump(out, open(outp, "w"), indent=1); print(json.dumps(out, indent=1))
