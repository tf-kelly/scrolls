"""Unit tests for sheet_check_core.py, mirroring src/test_sheet_check_core.cpp.
Usage: python3 test_sheet_check_core.py [GOLDEN_OUT_DIR]   (stdlib only)"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheet_check_core as core

fails = 0
def check(cond, msg):
    global fails
    if not cond:
        print("FAIL", msg); fails += 1

SCHEMA = json.dumps({
    "contract": "v1", "git": "abc", "branch": "<branch>",
    "region": {"origin_zyx": [4224, 2560, 640], "shape_zyx": [384, 384, 384]},
    "inputs": {}, "counts": {"pairs_flagged": 3},
    "clusters": [
        {"id": 0, "kind": "suspect_join", "n_pairs": 2, "n_patches": 3, "area_cm2": 0.0125,
         "centroid_zyx": [4300.5, 2700.25, 800.0], "bbox_zyx": [[4290, 2690, 790], [4310, 2710, 810]],
         "theta_deg": 130.0, "wrap_index_range": [3, 4], "patches": [1, 2, 3], "pairs": [[1, 2], [2, 3]], "max_risk": 0.91},
        {"id": 1, "kind": "wrong_turn", "n_pairs": 0, "n_patches": 1, "area_cm2": 0.002,
         "centroid_zyx": [4500, 2900, 1000], "bbox_zyx": [[4490, 2890, 990], [4510, 2910, 1010]],
         "theta_deg": 131.0, "wrap_index_range": [5, 5], "patches": [9], "pairs": [], "max_risk": None}]})

def bad(mutate, label):
    d = json.loads(SCHEMA); mutate(d)
    try:
        core.parse_report(json.dumps(d)); check(False, f"accepted: {label}")
    except core.ReportError:
        pass

# argv and swap
check(core.build_argv("/opt/vc", "/s/seg 1", "/v/vol.zarr", "/tmp/out") ==
      ["/opt/vc", "--segment", "/s/seg 1", "--volume", "/v/vol.zarr", "--out", "/tmp/out"], "argv")
check(core.to_vc3d_xyz([10.0, 20.0, 30.0]) == [30.0, 20.0, 10.0], "zyx -> xyz")
# schema
r = core.parse_report(SCHEMA)
check(r["region_origin_zyx"] == [4224, 2560, 640] and r["pairs_flagged"] == 3 and len(r["clusters"]) == 2, "schema")
a, b_ = r["clusters"]
check(a["kind"] == "suspect_join" and a["centroid_zyx"] == [4300.5, 2700.25, 800.0] and a["max_risk"] == 0.91, "cluster 0")
check(b_["max_risk"] is None, "null max_risk")
check(core.describe(a) == "#0 suspect_join  z=4300 y=2700 x=800  pairs=2 patches=3  0.013 cm2  switch=0.91", core.describe(a))
# errors (same cases as C++)
for text in ("not json", "[]"):
    try: core.parse_report(text); check(False, f"accepted {text!r}")
    except core.ReportError: pass
bad(lambda d: d.update(contract="v2"), "contract v2")
bad(lambda d: d["region"].update(origin_zyx=[1, 2]), "2-vector origin")
bad(lambda d: d.update(clusterz=d.pop("clusters")), "no clusters")
bad(lambda d: d["clusters"][1].update(kind="other"), "unknown kind")
bad(lambda d: d["clusters"][1].update(centroid_xyz=d["clusters"][1].pop("centroid_zyx")), "centroid_xyz")
bad(lambda d: d["clusters"][1].update(bbox_zyx=[[1, 2, 3]]), "1-corner bbox")
bad(lambda d: d["clusters"][1].update(id="1"), "string id")
bad(lambda d: d["clusters"][1].update(id=True), "bool id")
bad(lambda d: d.update(status="error", error="bad segment"), "status error")
check(core.parse_report(json.dumps(dict(json.loads(SCHEMA), status="ok")))["status"] == "ok", "status ok")
check("risk" not in core.describe(a), "never labelled risk")
check(core.inside_region(r, a) and "outside" not in core.describe_in(r, a), "inside region")
o = dict(b_, centroid_zyx=[5035.0, 2936.0, 934.0]); check(core.describe_in(r, o).endswith("[outside overlay region]"), "outside")
check(not core.inside_region(r, dict(b_, centroid_zyx=[4608.0, 2600.0, 700.0])), "upper bound exclusive")
# A10.2: overlay_region, when present, decides the tag; region keeps its meaning; malformed is rejected
_d = json.loads(SCHEMA); _d["overlay_region"] = {"origin_zyx": [3712, 2176, 384], "shape_zyx": [1408, 896, 1152]}
r2 = core.parse_report(json.dumps(_d))
check(r2["region_origin_zyx"] == [4224, 2560, 640] and r2["overlay_origin_zyx"] == [3712, 2176, 384], "overlay_region parsed")
check(core.inside_region(r2, o) and "outside" not in core.describe_in(r2, o), "inside overlay_region, outside region")
check(not core.inside_region(r2, dict(b_, centroid_zyx=[5120.0, 2936.0, 934.0])), "overlay_region upper bound exclusive")
_d["overlay_region"] = {"origin_zyx": [3712, 2176]}
try:
    core.parse_report(json.dumps(_d)); check(False, "malformed overlay_region rejected")
except core.ReportError:
    pass
# overlay choice and guard
with tempfile.TemporaryDirectory() as t:
    check(core.choose_overlay(t) is None, "no overlay")
    os.mkdir(os.path.join(t, "overlay.zarr")); check(core.choose_overlay(t).endswith("overlay.zarr"), "overlay.zarr")
    os.mkdir(os.path.join(t, "overlay_vc3d.zarr")); check(core.choose_overlay(t).endswith("overlay_vc3d.zarr"), "prefer view")
    o = os.path.join(t, "overlay.zarr")
    check(core.overlay_placement_problem(o) == "", "no .zattrs")
    def attrs(tr):
        ds = {"path": "0", "coordinateTransformations": [{"type": "scale", "scale": [7.91] * 3}] + tr}
        json.dump({"multiscales": [{"datasets": [ds]}]}, open(os.path.join(o, ".zattrs"), "w"))
    attrs([]); check(core.overlay_placement_problem(o) == "", "scale only")
    attrs([{"type": "translation", "translation": [0, 0, 0]}]); check(core.overlay_placement_problem(o) == "", "zero translation")
    attrs([{"type": "translation", "translation": [33411.84, 20249.6, 5062.4]}])
    check("translation" in core.overlay_placement_problem(o), "non-zero translation refused")
    v3 = os.path.join(t, "v3.zarr"); os.mkdir(v3)
    json.dump({"zarr_format": 3, "node_type": "group", "attributes": {"multiscales": [{"datasets": [
        {"path": "0", "coordinateTransformations": [{"type": "translation", "translation": [1, 0, 0]}]}]}]}},
        open(os.path.join(v3, "zarr.json"), "w"))
    check("translation" in core.overlay_placement_problem(v3), "v3 translation refused")
# golden: fixture v1.4 (example_outputs.py region A, full-frame overlay, 51 clusters, A10.2 overlay_region)
if len(sys.argv) > 1:
    g = sys.argv[1]
    r = core.parse_report(open(os.path.join(g, "report.json")).read())
    check(r["status"] == "ok", "golden status")
    check(r["region_origin_zyx"] == [4224, 2560, 640] and r["region_shape_zyx"] == [384, 384, 384], "golden region")
    kinds = [c["kind"] for c in r["clusters"]]
    check(r["pairs_flagged"] == 92 and kinds.count("suspect_join") == 30 and kinds.count("wrong_turn") == 21, "golden clusters")
    check(r["overlay_origin_zyx"] == [3712, 2176, 384] and r["overlay_shape_zyx"] == [1408, 896, 1152], "golden overlay_region")
    check(sum(not core.inside_region(r, c) for c in r["clusters"]) == 0, "every golden cluster inside overlay_region (A10.2)")
    ov = core.choose_overlay(g)
    check(ov.endswith("overlay.zarr") and core.overlay_placement_problem(ov) == "", "golden overlay accepted (no translation)")
    print(f"golden: status={r['status']} clusters={len(kinds)} pairs_flagged={r['pairs_flagged']} guard=silent")
print("OK" if not fails else f"FAILED ({fails})"); sys.exit(1 if fails else 0)
