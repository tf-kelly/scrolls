"""Score blind deck 2 against PREREG.md.  score_bdeck2.py RESPONSES_JSON KEY_JSON OUT_JSON"""
import json, math, sys
from statistics import NormalDist
resp, key, outp = sys.argv[1:4]
R = {a["item"]: a for a in json.load(open(resp))["answers"]}
K = {it["id"]: it for it in json.load(open(key))["items"]}
assert set(R) == set(K)
z = NormalDist().inv_cdf; ANS = ("switch", "stays", "leaves", "cant")
ans = lambda i: R[i].get("answer") or "cant"


def wilson(k, n, zz=1.959964):
    if n == 0: return [None, None]
    p = k / n; d = 1 + zz * zz / n; c = (p + zz * zz / (2 * n)) / d; h = zz * math.sqrt(p * (1 - p) / n + zz * zz / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


G = {g: [i for i in K if K[i]["group"] == g] for g in ("R02", "R5", "ART", "DA", "DB", "UNK")}
out = {"groups": {}}
for g, ids in G.items():
    n = len(ids); cnt = {a: sum(ans(i) == a for i in ids) for a in ANS}
    out["groups"][g] = {"n": n, "counts": cnt, "rates": {a: round(cnt[a] / n, 4) if n else None for a in ANS},
                        "wilson95": {a: wilson(cnt[a], n) for a in ANS}}
sw = lambda ids: sum(ans(i) == "switch" for i in ids)
other = G["ART"] + G["DA"] + G["DB"]
h1_hit, h1_fa = sw(G["R02"]) / len(G["R02"]), sw(other) / len(other)
Hc, Fc = (sw(G["R02"]) + 0.5) / (len(G["R02"]) + 1), (sw(other) + 0.5) / (len(other) + 1)
r5 = G["R5"]; r5_sw = sw(r5) / len(r5); r5_lv = sum(ans(i) == "leaves" for i in r5) / len(r5)
art_sw = sw(G["ART"]) / len(G["ART"])
out["H1"] = {"switch_rate_R02": round(h1_hit, 4), "switch_rate_ART_DA_DB": round(h1_fa, 4), "n_R02": len(G["R02"]), "n_other": len(other),
             "d_prime_loglinear": round(z(Hc) - z(Fc), 3), "holds": bool(h1_hit >= 2 / 3 and h1_fa <= 1 / 4)}
out["H2"] = {"switch_rate_R5": round(r5_sw, 4), "leaves_rate_R5": round(r5_lv, 4), "holds": bool(r5_sw <= 1 / 3 and r5_lv >= 1 / 2)}
out["H3"] = {"switch_rate_ART": round(art_sw, 4), "holds": bool(art_sw <= 1 / 4)}
out["false_alarm_DA"] = f"{sw(G['DA'])}/{len(G['DA'])}"; out["false_alarm_DB"] = f"{sw(G['DB'])}/{len(G['DB'])}"
json.dump(out, open(outp, "w"), indent=1); print(json.dumps(out, indent=1))
