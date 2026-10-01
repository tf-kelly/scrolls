"""Pixel-exact placement probe, in-app (see make_probe.py). Usage: probe_inapp.py WORK_CFX OUT VARIANT
Method: the plugin's dock jump sets the focus POI to voxel+0.25 (all slice planes pass through it);
each slice viewer is zoomed to VC3D's max (128 px/voxel) and grabbed alone via screenshot.capture;
pixels 25 px diagonally off the image centre (about 0.2 voxel, clear of the crosshair and POI marker)
are compared with VC3D's own fire LUT at window [0.5, 2] with overlay opacity 1:
value 1 -> (255,62,0), value 2 -> (255,255,255), 0 -> not blended (base CT).
"""
import glob, json, os, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "inapp"))
from bridge import Bridge
from inapp_contract_util import dock_rows_y  # noqa
fx, out, variant = sys.argv[1], sys.argv[2], sys.argv[3]
COL = {1: (255, 62, 0), 2: (255, 255, 255)}
VIEWERS = ["v2", "v3", "v4"]
def xdo(*a): subprocess.run(["xdotool", *a], check=True)
def shot(name): p = os.path.join(out, name); subprocess.run(["import", "-window", "root", p], check=True); return p
def pixels(png, pts):
    fmt = " ".join(f"%[pixel:p{{{x},{y}}}]" for x, y in pts)
    s = subprocess.run(["convert", png, "-format", fmt, "info:"], capture_output=True, text=True, check=True).stdout
    vals = []
    for tok in s.replace("srgba(", "srgb(").split("srgb(")[1:]:
        vals.append(tuple(int(float(v)) for v in tok.split(")")[0].split(",")[:3]))
    return vals
def size(png):
    w, h = subprocess.run(["identify", "-format", "%w %h", png], capture_output=True, text=True, check=True).stdout.split()
    return int(w), int(h)
def classify(c):
    for v, ref in COL.items():
        if all(abs(a - b) <= 2 for a, b in zip(c, ref)): return v
    return 0

b = Bridge("/tmp/vc3d-inapp"); res = {"variant": variant, "captures": []}
proj = os.path.join(fx, "project.volpkg.json")
b.call("project.create", path=proj, volume=os.path.join(fx, "volumes", os.environ.get("VP_BASE_VOLUME", "ct_A_view.zarr")), overwrite=True)
b.call("volume.open", path=proj); time.sleep(3)
b.call("segments.attach", location=os.path.join(fx, "paths")); time.sleep(3)
b.call("segments.activate", segmentId="WSP_patch_150217"); time.sleep(3)
b.call("viewer.set_render_settings", showDirectionHints=False, showSurfaceNormals=False,
       planeIntersectionLinesVisible=False, intersectionOpacity=0.0)
xdo("mousemove", "268", "9"); xdo("click", "1"); time.sleep(1.5); xdo("key", "Down"); xdo("key", "Return"); time.sleep(8)
res["overlay_after_plugin"] = b.call("viewer.get_overlay")
if variant == "region":
    # The plugin refuses this overlay; attach it directly to observe VC3D's own behaviour.
    od = sorted(glob.glob(os.path.join(out, "cache", "*", "*", "sheet_check", "*")))[-1]
    b.call("volume.attach", location=os.path.join(od, "overlay.zarr")); time.sleep(3)
    ids = b.call("volume.list")["volumeIds"]; vid = [i for i in ids if "overlay" in i or "probe" in i][-1]
    res["region_attach_id"] = vid
    b.call("viewer.set_overlay", volumeId=vid, colormap="fire", window={"low": 0.5, "high": 2.0}, opacity=1.0)
else:
    b.call("viewer.set_overlay", opacity=1.0)
res["overlay_for_probe"] = b.call("viewer.get_overlay")
for v in VIEWERS:
    b.call("viewer.zoom", viewer=v, factor=1000.0)
res["viewers"] = b.call("state.get")["viewers"]
rep = json.load(open(sorted(glob.glob(os.path.join(out, "cache", "*", "*", "sheet_check", "*", "report.json")))[-1]))
y0, _ = dock_rows_y(shot("dock.png"))
def run_pass(tag, only=None):
    for i, c in enumerate(rep["clusters"]):
        if only and c["probe_name"] not in only: continue
        xdo("mousemove", "1200", str(y0 + 14 * i)); xdo("click", "--repeat", "2", "--delay", "80", "1"); time.sleep(1.5)
        f = b.call("state.get")["focusPoi"]["position"]
        want = [c["centroid_zyx"][2], c["centroid_zyx"][1], c["centroid_zyx"][0]]
        focus_ok = all(abs(a - b_) < 1e-3 for a, b_ in zip((f["x"], f["y"], f["z"]), want))
        for v in VIEWERS:
            png = os.path.join(out, f"{tag}_{i:02d}_{v}.png")
            try:
                b.call("screenshot.capture", target=v, filePath=png)
            except RuntimeError as e:
                if "-32009" not in str(e): raise
                res["captures"].append({"pass": tag, "i": i, "name": c["probe_name"], "viewer": v, "hidden": True})
                continue
            w, h = size(png); cx, cy = w // 2, h // 2
            px = pixels(png, [(cx + 25, cy + 25), (cx - 25, cy + 25), (cx + 25, cy - 25), (cx - 25, cy - 25)])
            cls = [classify(p) for p in px]
            res["captures"].append({"pass": tag, "i": i, "name": c["probe_name"], "voxel_scan_zyx": c["probe_voxel_scan_zyx"],
                                    "expect": c["probe_expect"], "viewer": v, "focus_ok": focus_ok, "img": [w, h],
                                    "rgb": px, "class": cls})
run_pass("overlay")
b.call("viewer.set_overlay", opacity=0.0)
run_pass("control", only={c["probe_name"] for c in rep["clusters"] if c["probe_expect"] > 0})
ov = [c for c in res["captures"] if c["pass"] == "overlay" and not c.get("hidden")]
bad = [c for c in ov if not c["focus_ok"] or set(c["class"]) != {c["expect"]}]
ctrl = [c for c in res["captures"] if c["pass"] == "control" and not c.get("hidden")]
res["hidden_viewers"] = sorted({c["viewer"] for c in res["captures"] if c.get("hidden")})
print("hidden viewers (not captured):", res["hidden_viewers"])
ctrl_bad = [c for c in ctrl if any(k != 0 for k in c["class"])]
print(f"PROBE {variant}: {len(ov) - len(bad)}/{len(ov)} captures match (all 4 pixels = expected value, focus exact); "
      f"controls with overlay off that look like overlay colours: {len(ctrl_bad)}/{len(ctrl)}")
for c in bad[:12]:
    print("  MISMATCH", c["name"], c["viewer"], "expect", c["expect"], "got", c["class"], c["rgb"][0], "focus_ok", c["focus_ok"])
json.dump(res, open(os.path.join(out, "probe_result.json"), "w"), indent=1)
sys.exit(0 if not bad and not ctrl_bad else 1)
