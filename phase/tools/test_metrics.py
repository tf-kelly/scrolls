#!/usr/bin/env python3
"""Reproduce ledger numbers exactly with phase/tools/metrics.py, from committed data only.

  1. SessN8-04 (iii-rf) M1 55.0% [53.6, 56.6]           page purity, P1c per-patch-layer labelling, 48-block interval
  2. SessN8-04 (ii)     M3 0.38 [0.18, 0.64] per cm²    cross-turn join density, same bootstrap stream
  3. SessN4-01          recall 0.867 [0.837, 0.897] and precision 0.824 [0.776, 0.865] at the blind (nested) threshold

The expected strings are parsed from phase/writeup/LEDGER.md itself, not typed in here. The remaining SessN8-04 numbers
are checked too, and every value is also compared at full precision with the stage JSON that the ledger cites
(p1c_purity.json, W4_results.json). metrics.py shares no code with the stage scripts.

Usage: python3 phase/tools/test_metrics.py [--full]
  --full also regenerates testdata/w4_nested_calls.csv from w3_stats.py (retrains X8b, ~1 min) and checks that it is
  byte-identical to the committed file."""
import csv
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

T = Path(__file__).resolve().parent; R = T.parents[1]
sys.path.insert(0, str(T))
import metrics as M  # noqa: E402

FAIL = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r}, ledger {want!r}")
    if not ok:
        FAIL.append(name)


def close(name, got, want, tol=1e-9):
    ok = abs(got - want) <= tol
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {got!r} vs stage JSON {want!r}")
    if not ok:
        FAIL.append(name)


def ledger_row(rid):
    for line in open(R / "phase/writeup/LEDGER.md"):
        if line.startswith(f"| {rid} |"):
            return line
    raise SystemExit(f"ledger row {rid} not found")


def ledger_fmt(x, nd, scale=1):
    """The ledger's rounding chain: stage JSONs store 4 decimals; notes then round that value half-up
    (e.g. 0.9955 -> "99.6", 0.855 -> "0.86"). Python's float formatting would give 99.5 / 0.85."""
    from decimal import ROUND_HALF_UP, Decimal
    return str((Decimal(str(round(float(x), 4))) * scale).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def pct(x):
    return ledger_fmt(x, 1, 100)


def f2(x):
    return ledger_fmt(x, 2)


def main(full=False):
    syn = M.synthetic_checks(); print("synthetic", syn)
    if not all(syn.values()):
        FAIL.append("synthetic")

    _need = [R / p for p in ("phase/writeup/LEDGER.md", "phase/writeup/W4_results.json", "phase/p1page/p1c_purity.json",
                                 "phase/x10/x7_v7_edges.csv", "phase/x5/rel.csv")]
    _miss = [str(p.relative_to(R)) for p in _need if not p.exists()]
    if _miss:   # release tree: the ledger-reproduction part needs private files (release script, coordinator 16:31)
        print("SKIP ledger reproduction: needs private-only files not in the release tree: " + ", ".join(_miss))
        print("\nSYNTHETIC PASS, LEDGER SKIPPED" if not FAIL else f"\nFAILED: {FAIL}")
        return 0 if not FAIL else 1

    # ------------------------------------------------------------------ SessN8-04: P1c page purity
    row = ledger_row("SessN8-04")
    m = re.search(r"\(ii\) ([\d.]+)% \[([\d.]+), ([\d.]+)\] / ([\d.]+)% \[([\d.]+), ([\d.]+)\] / ([\d.]+) \[([\d.]+), ([\d.]+)\]", row)
    ii_want = m.groups()
    m = re.search(r"\(iii-rf\) ([\d.]+)% \[([\d.]+), ([\d.]+)\] / ([\d.]+)% \[([\d.]+), ([\d.]+)\] / ([\d.]+) \[([\d.]+), ([\d.]+)\]", row)
    rf_want = m.groups()
    m = re.search(r"\(i\) ([\d.]+)% / ([\d.]+)% / ([\d.]+);", row); i_want = m.groups()
    m = re.search(r"\(iii-new\) ([\d.]+)% / ([\d.]+)% / ([\d.]+);", row); new_want = m.groups()

    area = M.bbox_area_mm2(R / "phase/x1/patches.csv")
    cz = {int(r["id"]): float(r["cz"]) for r in csv.DictReader(open(R / "phase/x1/patches.csv"))}
    kref, theta = {}, {}
    for r in csv.DictReader(open(R / "phase/x7/X7_v9_patch_k.csv")):
        p = int(r["patch"]); theta[p] = float(r["theta_from_theta0"]) % M.TWO_PI
        if r["k_ref"] != "":
            kref[p] = int(r["k_ref"])
    t = {p: kref[p] + theta[p] / M.TWO_PI for p in kref}
    flip1 = {M.jkey(*r[:2]) for r in csv.reader(open(R / "phase/x10/flip1_pairs.csv"))}
    U = sorted({M.jkey(*r[:2]) for r in csv.reader(open(R / "phase/x5/rel.csv"))} - flip1)
    bad = {int(x) for x in open(R / "phase/x5/badpatches_b.csv").read().split() if x.strip()}
    v7 = {M.jkey(r["patch_a"], r["patch_b"]): r for r in csv.DictReader(open(R / "phase/x10/x7_v7_edges.csv"))}

    def new_ok(k):  # (iii-new): v7 numbering-consistency filter (P1b definition)
        v = v7.get(k)
        if v is None:
            return True
        if int(v["sync_implied"]) != 0:
            return False
        for c in ("d_i", "d_ii"):
            x = v.get(c)
            if x not in (None, "", "None"):
                return abs(int(v["sync_implied"]) - int(float(x))) == 0
        return True
    variants = {"i_all": U, "ii_pipeline9_deletions": [k for k in U if k[0] not in bad and k[1] not in bad],
                "iii_new": [k for k in U if new_ok(k)],
                "iii_rf": [tuple(k) for k in json.load(open(R / "phase/p1page/p1b_rf_joins.json"))["kept"]]}
    nodes = sorted({p for k in U for p in k})
    blk = dict(zip(nodes, M.block_id(M.sector([theta.get(p, 0.0) for p in nodes]), M.zslab_fixed([cz[p] for p in nodes], 4096, 192))))
    stage = json.load(open(R / "phase/p1page/p1c_purity.json"))
    rng = np.random.default_rng(0); got = {}
    for name, E in variants.items():  # same order and single stream as P1c, so the intervals are the same draws
        recs = M.page_records(M.pages(E, nodes, area), E, area, *M.cross_per_patch_layer(t), t=t)
        s = M.summarize(recs); ci = M.page_bootstrap(recs, blk, rng)
        got[name] = (s, ci)
        for k_me, k_st in (("M1", "M1"), ("M2_patch", "M2"), ("M3_per_cm2", "M3_per_cm2"), ("page_area_cm2", "page_area_cm2")):
            close(f"{name} {k_me}", round(s[k_me], 4), stage[name]["point"][k_st], 0)
            close(f"{name} {k_me} ci95", [round(x, 4) for x in ci[k_me]] == stage[name]["ci95"][k_st], True, 0)
    s, ci = got["iii_rf"]
    check("[1] SessN8-04 (iii-rf) M1", (pct(s["M1"]), pct(ci["M1"][0]), pct(ci["M1"][1])), rf_want[0:3])
    s, ci = got["ii_pipeline9_deletions"]
    check("[2] SessN8-04 (ii) M3", (f2(s['M3_per_cm2']), f2(ci['M3_per_cm2'][0]), f2(ci['M3_per_cm2'][1])), ii_want[6:9])
    check("    SessN8-04 (ii) M1, M2", (pct(s["M1"]), pct(ci["M1"][0]), pct(ci["M1"][1]), pct(s["M2_patch"]), pct(ci["M2_patch"][0]), pct(ci["M2_patch"][1])), ii_want[0:6])
    s, ci = got["iii_rf"]
    check("    SessN8-04 (iii-rf) M2, M3", (pct(s["M2_patch"]), pct(ci["M2_patch"][0]), pct(ci["M2_patch"][1]),
                                        f2(s['M3_per_cm2']), f2(ci['M3_per_cm2'][0]), f2(ci['M3_per_cm2'][1])), rf_want[3:9])
    for name, want in (("i_all", i_want), ("iii_new", new_want)):
        s = got[name][0]
        check(f"    SessN8-04 {name} M1/M2/M3", (pct(s["M1"]), pct(s["M2_patch"]), f2(s['M3_per_cm2'])), want)

    # ------------------------------------------------------------------ SessN4-01: blind operating point + block CI
    row = ledger_row("SessN4-01")
    m = re.search(r"precision ([\d.]+) \[([\d.]+), ([\d.]+)\], recall ([\d.]+) \[([\d.]+), ([\d.]+)\] \(([\d,]+) pairs, (\d+) adjacent\)", row)
    w4_want = m.groups()
    calls = T / "testdata/w4_nested_calls.csv"
    if full:
        with tempfile.TemporaryDirectory() as d:
            regen = Path(d) / "w4.csv"
            subprocess.run([sys.executable, str(T / "testdata/make_w4_calls.py"), str(regen)], check=True)
            close("w4_nested_calls.csv regenerated byte-identical", regen.read_bytes() == calls.read_bytes(), True, 0)
    rows = list(csv.DictReader(open(calls)))
    call = np.array([int(r["call_nested"]) for r in rows]); y = np.array([int(r["truth"]) for r in rows]); b = np.array([int(r["block"]) for r in rows])
    pr = M.precision_recall(call, y); bs = M.pr_block_bootstrap(call, y, b, seed=5)
    check("[3] SessN4-01 precision, recall with block CIs, n, positives",
          (f"{pr['precision']:.3f}", f"{bs['precision_ci95'][0]:.3f}", f"{bs['precision_ci95'][1]:.3f}",
           f"{pr['recall']:.3f}", f"{bs['recall_ci95'][0]:.3f}", f"{bs['recall_ci95'][1]:.3f}", f"{pr['n']:,}", str(pr["positives"])), w4_want)
    st = json.load(open(R / "phase/writeup/W4_results.json"))["nested_all_heldout"]
    close("SessN4 precision", pr["precision"], st["precision"]); close("SessN4 recall", pr["recall"], st["recall"])
    close("SessN4 CIs", [round(x, 4) for x in bs["precision_ci95"] + bs["recall_ci95"]] == st["precision_block_ci95"] + st["recall_block_ci95"], True, 0)

    print("\nALL PASS" if not FAIL else f"\nFAILED: {FAIL}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main(full="--full" in sys.argv))
