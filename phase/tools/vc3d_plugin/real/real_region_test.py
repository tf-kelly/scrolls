"""In-app: plugin -> SessA's real checker. Usage: real_region_test.py WORK_CFX OUT MODE   (MODE region | segment)
region : VC_SHEET_CHECK is region_adapter.sh (SessA region mode, fixture A). Checks: guard silent, overlay loaded,
         dock row count = report clusters, and exact jumps to the first 3 clusters whose centroid is inside the region.
segment: VC_SHEET_CHECK is SessA's CLI itself, called by the plugin exactly as contract A4.2 says. Records the outcome."""
import glob, json, os, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "inapp"))
from bridge import Bridge
from inapp_contract_util import dock_rows_y
fx, out, mode = sys.argv[1:4]
def xdo(*a): subprocess.run(["xdotool", *a], check=True)
def shot(n): p = os.path.join(out, n); subprocess.run(["import", "-window", "root", p], check=True); return p
def log(): return open(os.path.join(out, "vc3d.log"), errors="replace").read()
b = Bridge("/tmp/vc3d-inapp"); res = {"mode": mode}; fails = []
proj = os.path.join(fx, "project.volpkg.json")
b.call("project.create", path=proj, volume=os.path.join(fx, "volumes", os.environ.get("VP_BASE_VOLUME", "ct_A_view.zarr")), overwrite=True)
b.call("volume.open", path=proj); time.sleep(3)
b.call("segments.attach", location=os.path.join(fx, "paths")); time.sleep(3)
b.call("segments.activate", segmentId="WSP_patch_150217"); time.sleep(3)
t0 = time.time()
xdo("mousemove", "268", "9"); xdo("click", "1"); time.sleep(1.5); xdo("key", "Down"); xdo("key", "Return")
for _ in range(600):  # the real checker takes about a minute
    if "dock rows=" in log() or "vc.sheet_check: error" in log(): break
    time.sleep(1)
time.sleep(3); res["plugin_seconds"] = round(time.time() - t0, 1)
res["log"] = [l for l in log().splitlines() if l.startswith("vc.sheet_check:")]
res["overlay_after"] = b.call("viewer.get_overlay")
shot("1_after_run.png")
if mode == "region":
    guard = [l for l in res["log"] if "non-zero OME translation" in l]
    if guard: fails.append("guard fired")
    if not res["overlay_after"]["volumeId"]: fails.append("overlay not loaded")
    rep = json.load(open(sorted(glob.glob(os.path.join(out, "cache", "*", "*", "sheet_check", "*", "report.json")))[-1]))
    rows = [l for l in res["log"] if "dock rows=" in l]
    res["dock_rows"] = int(rows[-1].split("=")[-1]) if rows else None
    res["report_clusters"] = len(rep["clusters"])
    if res["dock_rows"] != len(rep["clusters"]): fails.append(f"dock rows {res['dock_rows']} != {len(rep['clusters'])} clusters")
    o, s = rep["region"]["origin_zyx"], rep["region"]["shape_zyx"]
    inside = [i for i, c in enumerate(rep["clusters"]) if all(o[k] <= c["centroid_zyx"][k] < o[k] + s[k] for k in range(3))]
    res["inside_region_rows"] = inside
    y0, _ = dock_rows_y(os.path.join(out, "1_after_run.png"))
    res["jumps"] = []
    for n, i in enumerate(inside[:3]):
        xdo("mousemove", "1200", str(y0 + 14 * i)); xdo("click", "--repeat", "2", "--delay", "80", "1"); time.sleep(2)
        f = b.call("state.get")["focusPoi"]["position"]; z, y, x = rep["clusters"][i]["centroid_zyx"]
        ok = max(abs(f["x"] - x), abs(f["y"] - y), abs(f["z"] - z)) <= 1e-3
        res["jumps"].append({"row": i, "id": rep["clusters"][i]["id"], "kind": rep["clusters"][i]["kind"],
                             "centroid_zyx": [z, y, x], "focus_xyz": [f["x"], f["y"], f["z"]], "exact": ok})
        shot(f"2_jump_{n}_row{i}.png")
        if not ok: fails.append(f"jump row {i}: focus {f}")
else:
    res["overlay_loaded"] = bool(res["overlay_after"]["volumeId"])
    reps = sorted(glob.glob(os.path.join(out, "cache", "*", "*", "sheet_check", "*", "report.json")))
    res["report_json"] = json.load(open(reps[-1])) if reps else None
res["fails"] = fails
s = json.dumps(res, indent=1, default=str)
for a, b_ in ((out, "<run>"), (fx, "<work>/cfx")): s = s.replace(a, b_)
open(os.path.join(out, f"real_{mode}.json"), "w").write(s)
print(json.dumps({k: res.get(k) for k in ("plugin_seconds", "dock_rows", "report_clusters", "inside_region_rows", "jumps", "overlay_loaded")}, default=str)[:1500])
for l in res["log"]: print(" ", l[:300])
print(f"REAL {mode}:", "PASS" if not fails else "FAIL: " + "; ".join(fails))
sys.exit(1 if fails else 0)
