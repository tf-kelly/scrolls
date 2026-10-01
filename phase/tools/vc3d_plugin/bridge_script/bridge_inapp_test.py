"""In-app test of sheet_check_bridge.py against a running VC3D (--agent-bridge). Stub checker only.
Usage: bridge_inapp_test.py WORK_DIR OUT MODE PYTHON_WITH_ZARR   (MODE golden | legacy_translation | fail | invalid)"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sheet_check_bridge import Bridge
w, out, mode, py = sys.argv[1:5]
fx = os.path.join(w, "cfx"); SOCK = "/tmp/vc3d-inapp"
for _ in range(120):
    try: b = Bridge(SOCK); break
    except OSError: time.sleep(0.5)
proj = os.path.join(fx, "project.volpkg.json")
b.call("project.create", path=proj, volume=os.path.join(fx, "volumes/ct_A_view.zarr"), overwrite=True)
b.call("volume.open", path=proj); time.sleep(3)
b.call("segments.attach", location=os.path.join(fx, "paths")); time.sleep(3)
b.call("segments.activate", segmentId="WSP_patch_150217"); time.sleep(3)
env = dict(os.environ, STUB_GOLDEN=os.path.join(w, "golden", "A"), STUB_MODE=mode,
           VP_TOOLS=os.path.join(HERE, ".."), VP_PY=py, XDG_CACHE_HOME=os.path.join(out, "cache"))
p = subprocess.run([sys.executable, os.path.join(HERE, "sheet_check_bridge.py"), "--socket", SOCK,
                    "--checker", os.path.join(HERE, "..", "inapp", "stub_contract_cli")],
                   env=env, capture_output=True, text=True, timeout=300)
ov = b.call("viewer.get_overlay"); focus = b.call("state.get")["focusPoi"]["position"]
res = {"mode": mode, "rc": p.returncode, "stdout": p.stdout, "stderr": p.stderr[-2000:], "overlay": ov, "focus": focus}
fails = []
want_rc = {"golden": 0, "legacy_translation": 3, "fail": 2, "invalid": 2}[mode]
if p.returncode != want_rc: fails.append(f"rc {p.returncode}, expected {want_rc}")
if mode == "golden":
    if not ov["volumeId"]: fails.append("overlay not loaded")
    if (ov["windowLow"], ov["windowHigh"]) != (0.5, 2): fails.append("window not [0.5, 2]")
elif ov["volumeId"]: fails.append(f"overlay should not be loaded, got {ov['volumeId']}")
if mode in ("golden", "legacy_translation"):
    rep = json.load(open(os.path.join(w, "golden", "A", "report.json")))
    z, y, x = rep["clusters"][0]["centroid_zyx"]
    if max(abs(focus["x"] - x), abs(focus["y"] - y), abs(focus["z"] - z)) > 1e-3:
        fails.append(f"focus {focus}, expected centroid_zyx reversed {[x, y, z]}")
    if "centred on #0 " not in p.stdout: fails.append("first cluster not reported as centred")
    if f"#{rep['clusters'][-1]['id']} " not in p.stdout: fails.append("last cluster not listed on stdout")
    if " risk=" in p.stdout: fails.append("stdout labels the switch score 'risk'")
if mode == "legacy_translation" and "translation" not in p.stderr: fails.append("refusal reason missing")
if mode in ("fail", "invalid") and "exited with code" not in p.stderr: fails.append("checker failure not reported")
res["fails"] = fails
s = json.dumps(res, indent=1).replace(out, "<run>").replace(w, "<work>").replace(HERE, "<bridge_script>")
open(os.path.join(out, f"bridge_{mode}.json"), "w").write(s)
print(p.stdout.strip()); print(p.stderr.strip()[-600:])
print(f"BRIDGE {mode}:", "PASS" if not fails else "FAIL: " + "; ".join(fails))
sys.exit(1 if fails else 0)
