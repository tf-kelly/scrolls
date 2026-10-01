"""In-app test of Tools -> Sheet check on contract-v1 outputs (STUB CLI replaying golden outputs)."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from bridge import Bridge
from inapp_contract_util import dock_rows_y
fx, out, mode = sys.argv[1], sys.argv[2], sys.argv[3]
def xdo(*a): subprocess.run(["xdotool", *a], check=True)
def shot(name): subprocess.run(["import", "-window", "root", os.path.join(out, name)], check=True)
b = Bridge("/tmp/vc3d-inapp"); res = {"mode": mode}
proj = os.path.join(fx, "project.volpkg.json")
res["project.create"] = b.call("project.create", path=proj, volume=os.path.join(fx, "volumes", os.environ.get("VP_BASE_VOLUME", "ct_A_view.zarr")), overwrite=True)
res["volume.open"] = b.call("volume.open", path=proj); time.sleep(3)
res["segments.attach"] = b.call("segments.attach", location=os.path.join(fx, "paths")); time.sleep(3)
res["segments.list"] = b.call("segments.list")
res["segments.activate"] = b.call("segments.activate", segmentId="WSP_patch_150217"); time.sleep(3)
res["overlay_before"] = b.call("viewer.get_overlay")
shot("1_before.png")
xdo("mousemove", "268", "9"); xdo("click", "1"); time.sleep(1.5); shot("2_tools_menu.png")
xdo("key", "Down"); xdo("key", "Return"); time.sleep(10)
res["overlay_after"] = b.call("viewer.get_overlay")
res["volume.list"] = b.call("volume.list")
res["state_before_jump"] = b.call("state.get")
shot("3_after_run.png")
if mode in ("golden", "legacy_translation"):
    y0, y1 = dock_rows_y(os.path.join(out, "3_after_run.png")); res["dock_rows_y"] = [y0, y1]
    xdo("mousemove", "1200", str(y0)); xdo("click", "--repeat", "2", "--delay", "80", "1"); time.sleep(5)
    res["state_after_jump"] = b.call("state.get")
    shot("4_after_jump_row0.png")
    xdo("mousemove", "1200", str(y1)); xdo("click", "--repeat", "2", "--delay", "80", "1"); time.sleep(5)
    res["state_after_jump2"] = b.call("state.get")
    shot("5_after_jump_row1.png")
json.dump(res, open(os.path.join(out, "inapp_result.json"), "w"), indent=1, default=str)
for k in ("overlay_before", "overlay_after"):
    print(k, {kk: res[k][kk] for kk in ("volumeId", "colormap", "opacity", "windowLow", "windowHigh")})
for k in ("state_before_jump", "state_after_jump", "state_after_jump2"):
    if k in res: print(k, res[k].get("focusPoi"))

# Self-check: exit non-zero unless the expected in-app state was observed.
import glob
fails = []
vid = res["overlay_after"]["volumeId"]
if mode in ("legacy_translation", "fail", "invalid"):
    if vid: fails.append(f"overlay should not be loaded in mode {mode}, got {vid}")
else:
    if not vid: fails.append("overlay not loaded")
    if (res["overlay_after"]["windowLow"], res["overlay_after"]["windowHigh"]) != (0.5, 2): fails.append("overlay window not [0.5, 2]")
if mode in ("golden", "legacy_translation"):
    rep = json.load(open(sorted(glob.glob(os.path.join(out, "cache", "*", "*", "sheet_check", "*", "report.json")))[-1]))
    for k, c in (("state_after_jump", rep["clusters"][0]), ("state_after_jump2", rep["clusters"][1])):
        p = res[k]["focusPoi"]["position"]; z, y, x = c["centroid_zyx"]
        if max(abs(p["x"] - x), abs(p["y"] - y), abs(p["z"] - z)) > 1e-3:
            fails.append(f"{k}: focus {p}, expected centroid_zyx reversed {[x, y, z]}")
    res["expected_jumps_xyz"] = [c["centroid_zyx"][::-1] for c in rep["clusters"][:2]]
res["self_check_failures"] = fails
json.dump(res, open(os.path.join(out, "inapp_result.json"), "w"), indent=1, default=str)
print("SELF-CHECK", "PASS" if not fails else "FAIL: " + "; ".join(fails))
sys.exit(1 if fails else 0)
