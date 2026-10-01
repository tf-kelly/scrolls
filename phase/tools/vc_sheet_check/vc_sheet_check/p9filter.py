"""Contract §4.6 pipeline9 filter core: drop flagged joins from pipeline9's rel.csv.

rel.csv is pipeline9's aligner output (P9 format, no header): patch ids in the first two
columns, then flip and the affine terms. Rows are copied as raw bytes, so every kept row is
byte-identical to the input; only rows whose (unordered) patch pair is flagged are removed.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


def _key(a, b):
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


def filter_rel(rel_path, outdir, scored, threshold, head, restrict=None, reason="risk>=blind_threshold"):
    """scored: dicts patch_a, patch_b, risk, flagged, sep_um. restrict: optional patch set; rows with an end
    outside it are left out of both outputs (a region run only speaks for its own patches)."""
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    flagged = {(_key(r["patch_a"], r["patch_b"])): r for r in scored if int(r["flagged"])}
    kept = removed = skipped = 0
    rem = []
    with open(rel_path, "rb") as fi, open(outdir / "rel_filtered.csv", "wb") as fo:
        for line in fi:
            txt = line.decode("utf-8", "replace")
            parts = txt.split(",")
            try:
                k = _key(parts[0], parts[1])
            except (ValueError, IndexError):
                fo.write(line); kept += 1; continue      # header or malformed: pass through unchanged
            if restrict is not None and (k[0] not in restrict or k[1] not in restrict):
                skipped += 1; continue
            if k in flagged:
                removed += 1; rem.append(k); continue
            fo.write(line); kept += 1
    with open(outdir / "removed_joins.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patch_a", "patch_b", "risk", "sep_um", "contact", "reason"])
        for k in rem:
            r = flagged[k]; s = r.get("sep_um")
            w.writerow([k[0], k[1], repr(float(r["risk"])), s, int(s is not None and float(s) < 50), reason])
    info = dict(**head, rel_rows_kept=kept, rel_rows_removed=removed, rel_rows_outside_region=skipped,
                flagged_pairs=len(flagged), threshold=threshold, input=str(rel_path))
    json.dump(info, open(outdir / "filter.json", "w"), indent=1)
    return {k: v for k, v in info.items() if k not in head}
