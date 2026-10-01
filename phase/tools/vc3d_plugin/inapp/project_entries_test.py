"""In-app test of the project-file bookkeeping (plugin (c)). Usage: project_entries_test.py WORK_CFX OUT
1. Before opening, plant a sheet_check entry for another segment whose directory does not exist.
2. Run Tools -> Sheet check: the planted entry must be pruned and exactly one entry must exist for the segment.
3. Run it again: still exactly one entry for the segment, at the new location, and it is the overlay volume.
Exits non-zero on any mismatch. Uses the stub CLI in 'golden' mode.
"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bridge import Bridge
fx, out = sys.argv[1], sys.argv[2]
SEG = "WSP_patch_150217"
def xdo(*a): subprocess.run(["xdotool", *a], check=True)
def run_plugin():
    xdo("mousemove", "268", "9"); xdo("click", "1"); time.sleep(1.5); xdo("key", "Down"); xdo("key", "Return"); time.sleep(10)
def ours(proj):
    vols = json.load(open(proj))["volumes"]
    return [v for v in vols if isinstance(v, dict) and "sheet_check" in v.get("tags", [])]
b = Bridge("/tmp/vc3d-inapp"); res = {}; fails = []
proj = os.path.join(fx, "project.volpkg.json")
b.call("project.create", path=proj, volume=os.path.join(fx, "volumes", os.environ.get("VP_BASE_VOLUME", "ct_A_view.zarr")), overwrite=True)
doc = json.load(open(proj))
missing = os.path.join(out, "cache", "gone", "sheet_check", "other-19700101T000000000", "overlay.zarr")
doc["volumes"].append({"location": missing, "tags": ["sheet_check", "sheet_check_segment:other"]})
json.dump(doc, open(proj, "w"), indent=2)
res["open"] = b.call("volume.open", path=proj); time.sleep(3)
res["volumes_after_open"] = b.call("volume.list")
b.call("segments.attach", location=os.path.join(fx, "paths")); time.sleep(3)
b.call("segments.activate", segmentId=SEG); time.sleep(3)
res["project_before"] = ours(proj)
run_plugin()
res["project_after_run1"] = a1 = ours(proj); res["overlay_run1"] = b.call("viewer.get_overlay")["volumeId"]
if any(e["location"] == missing for e in a1): fails.append("stale entry not pruned")
if len(a1) != 1 or f"sheet_check_segment:{SEG}" not in a1[0]["tags"]: fails.append(f"run 1: expected one entry for {SEG}, got {a1}")
run_plugin()
res["project_after_run2"] = a2 = ours(proj); res["overlay_run2"] = b.call("viewer.get_overlay")["volumeId"]
if len(a2) != 1: fails.append(f"run 2: expected one entry, got {len(a2)}")
elif a1 and a2[0]["location"] == a1[0]["location"]: fails.append("run 2 did not replace the entry")
elif not a2[0]["location"].endswith("overlay.zarr"): fails.append("run 2 entry is not an overlay")
if res["overlay_run2"] == res["overlay_run1"] or not res["overlay_run2"]: fails.append("overlay volume not switched to run 2")
res["volume_list_end"] = b.call("volume.list")
res["fails"] = fails
s = json.dumps(res, indent=1).replace(out, "<run>").replace(fx, "<work>")
open(os.path.join(out, "project_entries_result.json"), "w").write(s)
print(s[:3000]); print("PROJECT-ENTRIES", "PASS" if not fails else "FAIL: " + "; ".join(fails))
sys.exit(1 if fails else 0)
