"""In-app test of the plugin's --axis-file wiring (SessD-5 (1)) against SessA's REAL vc_sheet_check (segment mode).
Usage: axis_test.py WORK_CFX OUT CASE AXIS_CSV
  A  project "umbilicus" field -> a header-less 'z, y, x' text file (villa text layout, readable by SessA)
  B  <package root>/umbilicus.json (villa json layout, found by VC3D's discovery; SessA cannot parse json)
  C  no umbilicus anywhere -> segment mode disabled with a one-line reason, checker not launched
Axis points come from the contract's axis file (phase/tools/axis/pherc1667_x3slab2_axis.csv, header 'z,y,x').
The segment is attached from a private copy under OUT/seg/paths: VC3D also searches the parent and grandparent of each
segment entry, and the in-app fixture keeps a umbilicus.json in cfx/ for the other tests."""
import glob, json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "inapp"))
from bridge import Bridge
fx, out, case, axis_csv = sys.argv[1:5]
def xdo(*a): subprocess.run(["xdotool", *a], check=True)
def log(): return open(os.path.join(out, "vc3d.log"), errors="replace").read()
pts = [l.strip() for l in open(axis_csv) if l.strip() and not l.startswith("z")]
pkg = os.path.join(out, "pkg"); os.makedirs(pkg, exist_ok=True)       # package root for this case
seg = os.path.join(out, "seg", "paths")                               # private segment entry (see docstring)
shutil.copytree(os.path.join(fx, "paths"), seg)
for f in ("umbilicus.json", "estimated_umbilicus.json"):
    for d in (pkg, os.path.dirname(seg), out):
        assert not os.path.exists(os.path.join(d, f)), f"stray {f} in {d}"
proj = os.path.join(pkg, "project.volpkg.json")
b = Bridge("/tmp/vc3d-inapp")
b.call("project.create", path=proj, volume=os.path.join(fx, "volumes", os.environ.get("VP_BASE_VOLUME", "ct_A_view.zarr")), overwrite=True)
expect_axis = None
if case == "A":
    txt = os.path.join(pkg, "umbilicus_zyx.txt"); open(txt, "w").write("\n".join(pts) + "\n")
    doc = json.load(open(proj)); doc["umbilicus"] = txt; json.dump(doc, open(proj, "w"), indent=2); expect_axis = txt
elif case == "B":
    js = os.path.join(pkg, "umbilicus.json")
    json.dump({"points": [[float(v) for v in p.split(",")] for p in pts]}, open(js, "w")); expect_axis = js
b.call("volume.open", path=proj); time.sleep(3)
b.call("segments.attach", location=seg); time.sleep(3)
b.call("segments.activate", segmentId="WSP_patch_150217"); time.sleep(3)
xdo("mousemove", "268", "9"); xdo("click", "1"); time.sleep(1.5); xdo("key", "Down"); xdo("key", "Return")
for _ in range(900):
    if "dock rows=" in log() or "vc.sheet_check: error" in log(): break
    time.sleep(1)
time.sleep(2)
lines = [l for l in log().splitlines() if l.startswith("vc.sheet_check:")]
started = [l for l in lines if ": start " in l]
res = {"case": case, "expect_axis": expect_axis, "log": lines, "checker_output_tail": log().splitlines()[-12:],
       "overlay_after": b.call("viewer.get_overlay")}
fails = []
if case == "C":
    if started: fails.append("checker was launched without an axis")
    if not any("Segment mode disabled" in l for l in lines): fails.append("no one-line disable reason")
else:
    if not started: fails.append("checker not launched")
    elif f"--axis-file {expect_axis}" not in started[0]: fails.append("axis not passed as expected")
reps = sorted(glob.glob(os.path.join(out, "cache", "*", "*", "sheet_check", "*", "report.json")))
res["report_status"] = json.load(open(reps[-1])).get("status") if reps else None
res["report_error"] = json.load(open(reps[-1])).get("error") if reps else None
res["fails"] = fails
s = json.dumps(res, indent=1).replace(out, "<run>").replace(fx, "<work>/cfx")
open(os.path.join(out, f"axis_{case}.json"), "w").write(s)
for l in lines: print(" ", l.replace(out, "<run>")[:330])
print(f"AXIS {case}:", "PASS" if not fails else "FAIL: " + "; ".join(fails), "| report status:", res["report_status"], res["report_error"] or "")
sys.exit(1 if fails else 0)
