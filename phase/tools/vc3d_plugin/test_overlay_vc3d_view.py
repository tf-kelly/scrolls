"""Check overlay_vc3d_view.py on the fixture CT (phase/data_small/fixture/ct.zarr, which keeps its v1 OME translation).
Since Amendment 4 the contract overlay is written full-frame, so the view writer is only needed for that CT.

Usage: python3 test_overlay_vc3d_view.py   (needs zarr to read back)
The view read at the region must equal the source level 0 exactly; everything
outside must be fill (0).
"""
import json, os, sys, tempfile
import numpy as np, zarr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from overlay_vc3d_view import write_view

SCAN = (11174, 3340, 3440)  # contract §1, PHerc1667 20231117161658 level 0
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
fails = 0


def check(cond, msg):
    global fails
    print(("PASS  " if cond else "FAIL  ") + msg)
    fails += 0 if cond else 1


def roundtrip(src, label):
    with tempfile.TemporaryDirectory() as t:
        dst = os.path.join(t, "view.zarr")
        info = write_view(src, dst, SCAN, "test_" + label, label)
        a = zarr.open_array(os.path.join(src, "0"), mode="r")[:]
        v = zarr.open_array(os.path.join(dst, "0"), mode="r")
        o = info["origin_zyx"]; s = a.shape
        check(tuple(v.shape) == SCAN, f"{label}: view shape is the scan shape {SCAN}")
        check(v.dtype == a.dtype, f"{label}: dtype kept ({a.dtype})")
        inside = v[o[0]:o[0]+s[0], o[1]:o[1]+s[1], o[2]:o[2]+s[2]]
        check(np.array_equal(inside, a), f"{label}: view at origin {o} equals source level 0 (sum {int(a.astype(np.int64).sum())})")
        pad = 128
        ring = v[o[0]-pad:o[0]+s[0]+pad, o[1]-pad:o[1]+s[1]+pad, o[2]-pad:o[2]+s[2]+pad].astype(np.int64)
        ring[pad:pad+s[0], pad:pad+s[1], pad:pad+s[2]] = 0
        check(not ring.any(), f"{label}: one chunk of margin around the region is all fill")
        attrs = json.load(open(os.path.join(dst, ".zattrs")))
        tr = [t for t in attrs["multiscales"][0]["datasets"][0]["coordinateTransformations"] if t["type"] == "translation"]
        check(not tr, f"{label}: no translation in the view (VC3D requires zero)")
        meta = json.load(open(os.path.join(dst, "meta.json")))
        check((meta["slices"], meta["height"], meta["width"]) == SCAN, f"{label}: meta.json slices/height/width = scan z/y/x")
        return info


info = roundtrip(os.path.join(REPO, "phase/data_small/fixture/ct.zarr"), "fixture_ct")
check(info["origin_zyx"] == [4224, 2560, 640], "fixture CT origin is region A (4224, 2560, 640)")
print("ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
