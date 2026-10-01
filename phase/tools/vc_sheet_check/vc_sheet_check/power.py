"""Power statement for segment-mode clusters (SessA-4 (c); protocol validation/SessA-4_PROTOCOL.md).

The calibration (`power_calibration.json`, beside this file) is written from SessA-4 (b)'s planted-jump measurements only:
the null-derived cluster size m*, the calibration density rho_b (pairs/cm2) and testable share c_b, and for each built,
clean-before jump the peak number of flagged midpoints within 200 um in its box after planting.

For a run with density rho and testable share c:
  s = rho * c / (rho_b * c_b)                         (thinning of flagged pairs, at most 1)
  power = mean_k P(Binomial(peak_k, s) >= m*)         for s < 1
  power = (b)'s measured sensitivity                   for s >= 1 (nothing is extrapolated above the measured density)
A run with power < 0.5 prints and records "not a clean-segment test".
"""
from __future__ import annotations

import json
from pathlib import Path

CAL = Path(__file__).resolve().parent / "power_calibration.json"
THRESHOLD = 0.5


def load():
    return json.load(open(CAL)) if CAL.exists() else None


def estimate(pairs_per_cm2, testable_share, cal=None):
    cal = cal if cal is not None else load()
    if cal is None:
        return dict(power=None, statement="power unknown (no SessA-4 calibration): not a clean-segment test",
                    clean_segment_test=False)
    from scipy.stats import binom
    s = (pairs_per_cm2 * testable_share) / (cal["rho_b"] * cal["c_b"]) if cal["rho_b"] * cal["c_b"] > 0 else 0.0
    if s >= 1:
        p = cal["sensitivity"]; how = "at or above the calibration density: the measured sensitivity (not extrapolated)"
    else:
        peaks = cal["peaks_after"]
        p = sum(binom.sf(cal["m_star"] - 1, k, s) for k in peaks) / len(peaks) if peaks else 0.0
        how = f"binomial thinning of the calibration jumps' peaks by s = {s:.3f}"
    ok = p is not None and p >= THRESHOLD
    return dict(power=p, thinning_s=s, method=how, m_star=cal["m_star"], threshold=THRESHOLD,
                calibration=dict(rho_b=cal["rho_b"], c_b=cal["c_b"], sensitivity=cal["sensitivity"],
                                 sensitivity_ci95=cal.get("sensitivity_ci95"), fp_per_cm2=cal.get("fp_per_cm2"),
                                 fp_per_cm2_ci95=cal.get("fp_per_cm2_ci95"), n_jumps=len(cal["peaks_after"]), source=cal.get("source")),
                clean_segment_test=bool(ok),
                statement=(f"power {p:.2f}: a 2 mm layer jump would be flagged with this probability" if ok
                           else f"power {p:.2f} < {THRESHOLD}: not a clean-segment test"))
