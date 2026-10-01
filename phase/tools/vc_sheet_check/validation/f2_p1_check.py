#!/usr/bin/env python3
"""F2 page 1 (F123_PROTOCOL.md + amendment): segment check on the patches under page 1's off-modal area (after index),
largest off-modal area first; one JSON line per patch as it finishes.
Usage: f2_p1_check.py LIST_JSON GOOD_ZIP BAD_ZIP AXIS WORK OUT.jsonl [--workers 2]"""
import json, re, subprocess, sys, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CT = "https://dl.ash2txt.org/full-scrolls/Scroll4/PHerc1667.volpkg/volumes_zarr/20231117161658.zarr"
VENV = Path(sys.executable).parent


def main():
    a = sys.argv[1:]; L = json.load(open(a[0])); gz, bz, axf, work, out = a[1:6]; work = Path(work)
    nw = int(a[a.index("--workers") + 1]) if "--workers" in a else 2
    order = L["patches"]; nodes = dict(zip(L["patches"], L["nodes"])); want = set(order); where = {}
    for zn in (gz, bz):
        z = zipfile.ZipFile(zn)
        for nm in z.namelist():
            m = re.search(r"(?:^|/)patch_(\d+)/x\.tif$", nm)
            if m and int(m.group(1)) in want: where[int(m.group(1))] = (zn, nm[:-5])
    fo = open(out, "a")

    def run(p):
        zn, pre = where[p]; z = zipfile.ZipFile(zn)
        for nm in z.namelist():
            if nm.startswith(pre): z.extract(nm, work / "src")
        o = work / "runs" / f"patch_{p}"
        if not (o / "report.json").exists():
            subprocess.run([str(VENV / "vc_sheet_check"), "--segment", str(work / "src" / pre), "--volume", CT, "--axis-file", axf, "--out", str(o)],
                           capture_output=True, text=True, timeout=900, cwd=str(Path(__file__).resolve().parents[4]))
        try:
            R = json.load(open(o / "report.json")); cl = R.get("clusters") or []
            rec = dict(patch=p, off_nodes=nodes[p], outcome="fail" if cl else "pass", clusters=len(cl), power=(R.get("power") or {}).get("power"),
                       area_cm2=R["coverage"]["area_cm2"], testable_share=R["coverage"]["testable_share"])
        except Exception as e:
            rec = dict(patch=p, off_nodes=nodes[p], outcome="error", why=repr(e)[:200])
        fo.write(json.dumps(rec) + "\n"); fo.flush(); return rec
    with ThreadPoolExecutor(nw) as ex:
        list(ex.map(run, order))


if __name__ == "__main__":
    main()
