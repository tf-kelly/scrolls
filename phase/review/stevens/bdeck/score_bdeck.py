"""Score the blind switch / no-switch deck against PREREG.md.  score_bdeck.py RESPONSES_JSON KEY_JSON OUT_JSON"""
import json, sys
from statistics import NormalDist
resp, key, outp = sys.argv[1:4]
R = {a["item"]: a for a in json.load(open(resp))["answers"]}
K = {it["id"]: it for it in json.load(open(key))["items"]}
assert set(R) == set(K) and len(K) == 30
z = NormalDist().inv_cdf
ans = lambda i: (R[i].get("answer") or "cant")
cls = lambda c: [i for i in K if K[i]["class"] == c]
real, art, dec = cls("real"), cls("artefact"), cls("decoy"); other = art + dec
sw = lambda ids: sum(ans(i) == "switch" for i in ids)
ct = lambda ids: sum(ans(i) == "cant" for i in ids)
H, F = sw(real) / len(real), sw(other) / len(other)
Hc, Fc = (sw(real) + 0.5) / (len(real) + 1), (sw(other) + 0.5) / (len(other) + 1)
defin = lambda ids: [i for i in ids if ans(i) != "cant"]
out = {"n": {"real": len(real), "artefact": len(art), "decoy": len(dec)},
       "switch": {"real": sw(real), "artefact": sw(art), "decoy": sw(dec)},
       "cant_tell": {"real": ct(real), "artefact": ct(art), "decoy": ct(dec)},
       "hit_rate": round(H, 4), "false_alarm_rate": round(F, 4),
       "false_alarm_artefact": f"{sw(art)}/{len(art)}", "false_alarm_decoy": f"{sw(dec)}/{len(dec)}",
       "d_prime_loglinear": round(z(Hc) - z(Fc), 3),
       "excluding_cant_tell": {"hit_rate": round(sw(real) / max(len(defin(real)), 1), 4), "n_real": len(defin(real)),
                               "false_alarm_rate": round(sw(other) / max(len(defin(other)), 1), 4), "n_other": len(defin(other))},
       "per_page": {str(p): {c: f"{sw([i for i in cls(c) if K[i]['page'] == p])}/{len([i for i in cls(c) if K[i]['page'] == p])}"
                             for c in ("real", "artefact", "decoy") if any(K[i]['page'] == p for i in cls(c))} for p in (0, 1, 2, 5)},
       "rule": "stands iff hit_rate >= 2/3 and false_alarm_rate <= 1/4 (cant-tell = not switch)",
       "switch_finding_stands": bool(sw(real) >= 8 and sw(other) <= 4)}
json.dump(out, open(outp, "w"), indent=1); print(json.dumps(out, indent=1))
