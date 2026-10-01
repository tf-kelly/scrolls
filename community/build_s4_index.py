"""Build winding.csv and contradictions.json for the Scroll 4 community package (local only).
Inputs: committed wrap_index.csv / unsatisfied.csv (copied into this work dir, hashes checked below)."""
import csv, json, math, sys
from collections import OrderedDict
from pathlib import Path

WORK = Path(__file__).parent
OUT = Path(sys.argv[1])
SRC_SHA = {"wrap_index.csv": "1c0b7d308f347d99112d6da50686955011490e9bad2980fab5cffd86fcf4aa65",
           "unsatisfied.csv": "6694e9644159a17f530f3a2c94a579e341bcfabb798d649b8f01e0c3984a50c4"}
import hashlib
for f, h in SRC_SHA.items():
    assert hashlib.sha256((WORK / f).read_bytes()).hexdigest() == h, f

S = 1  # handedness chosen by the solve (wrap_index.json s_chosen)


def seam(t1, t2):  # solve.py cross(): +1 / -1 if the shorter path from t1 to t2 passes theta = 0 upward / downward
    e = t1 + ((t2 - t1 + math.pi) % (2 * math.pi) - math.pi)
    return 1 if e >= 2 * math.pi else (-1 if e < 0 else 0)


W = list(csv.DictReader(open(WORK / "wrap_index.csv")))
th = {int(r["patch"]): float(r["thN"]) for r in W}
K = {int(r["patch"]): int(r["k_q3c"]) for r in W}
with open(OUT / "winding.csv", "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["patch_id", "component", "winding", "theta_rad"])
    for r in W:
        w.writerow([r["patch"], r["component"], r["k_q3c"], r["thN"]])

KIND = {"i": "crossing_count", "ii": "radial_separation", "iii": "same_wrap_rule"}
num = lambda v, t: None if v in ("", "nan", "None") else t(v)
joins = OrderedDict()
for r in csv.DictReader(open(WORK / "unsatisfied.csv")):
    a, b = int(r["patch_a"]), int(r["patch_b"])
    c = seam(th[a], th[b])
    req, sol, res = int(r["observed"]), int(r["solved"]), int(r["residual"])
    assert sol == K[b] - K[a] and res == sol - req
    if r["type"] == "i": assert req - int(r["d_i"]) == S * c
    if r["type"] == "ii": assert req - int(r["d_ii"]) == S * c
    j = joins.get((a, b))
    if j is None:
        j = joins[(a, b)] = OrderedDict(
            patches=[a, b],
            measurements=OrderedDict(
                crossing_count_median=num(r["d_i"], int),
                radial_separation_um=num(r["sep_ii_um"], float),
                radial_separation_in_spacings=num(r["d_ii"], int),
                max_normal_separation_um=num(r["max_sep_um"], float),
                exceeds_same_wrap_threshold={"True": True, "False": False}[r["stevens"]],
                witness_verdict=r["verdict"] or None,
                witness_testable_points=num(r["n_testable"], int),
                witness_agreement=num(r["agreement"], float)),
            constraints=[])
    j["constraints"].append(OrderedDict(
        constraint=KIND[r["type"]], value_before_seam=req - S * c, seam_crossing=c,
        required_difference=req, solved_difference=sol, violation=res, weight=float(r["weight"])))

doc = OrderedDict(
    about="Joins (patch pairs) where the solved windings violate at least one constraint of the whole-scroll winding solve. "
          "Nothing was removed for being contradictory: every join listed here stayed in the solve, and all but one are also in "
          "same_windings.json / relative_windings.json (the exception, patches 147037 and 147797, lost all its point pairs "
          "to the fitter-input loader filter's tie check). "
          "See README.md for field meanings.",
    difference_convention="required_difference and solved_difference refer to winding[patches[1]] - winding[patches[0]] in winding.csv; "
                          "violation = solved_difference - required_difference; required_difference = value_before_seam + seam_crossing.",
    n_joins=len(joins), n_violated_constraints=sum(len(j["constraints"]) for j in joins.values()),
    joins=list(joins.values()))
with open(OUT / "contradictions.json", "w") as f:
    f.write("{\n")
    for k in ("about", "difference_convention", "n_joins", "n_violated_constraints"):
        f.write(f" {json.dumps(k)}: {json.dumps(doc[k])},\n")
    f.write(' "joins": [\n')
    for i, j in enumerate(doc["joins"]):
        f.write("  " + json.dumps(j, separators=(",", ":")) + (",\n" if i < len(doc["joins"]) - 1 else "\n"))
    f.write(" ]\n}\n")
json.load(open(OUT / "contradictions.json"))
print("winding rows", len(W), "joins", doc["n_joins"], "constraints", doc["n_violated_constraints"])
