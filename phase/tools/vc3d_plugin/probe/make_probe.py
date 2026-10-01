"""Write the placement-probe overlays and their probe report.json.

Usage: make_probe.py OUT_DIR   (needs zarr>=3)
Writes OUT_DIR/{v2,v3,region}/ each with report.json + overlay_vc3d.zarr (v2, v3) or overlay.zarr (region):
  v2      full-frame sparse OME-Zarr v2, zero translation (the contract's new overlay form)
  v3      the same array as Zarr v3
  region  contract-v1 §4.2 form: 384^3 region A, translation = origin x 7.91 (VC3D bug check)
report.json lists one "cluster" per test voxel with centroid = voxel + 0.25 (inside the voxel whether VC3D
floors or rounds) and the value the probe holds there in "probe_expect".
"""
import json, os, sys, shutil
import numpy as np, zarr

HERE = os.path.dirname(os.path.abspath(__file__))
T = json.load(open(os.path.join(HERE, "probe_targets.json")))
SCAN = tuple(T["scan_shape_zyx"]); P2 = np.array(T["P2_zyx"]); P1 = np.array(T["P1_zyx"])
ORIGIN = np.array([4224, 2560, 640]); RSHAPE = (384, 384, 384); VS = 7.91
E = [np.array(e) for e in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]

def voxels():
    v = {tuple(P2): 2, tuple(P1): 1}
    for e in E:
        v[tuple(P1 + e)] = 1
    return v

def tests():
    vox = voxels(); out = [("P2", P2)] + [(f"P2{tuple(e)}", P2 + e) for e in E] + [("P1", P1)] \
        + [(f"P1{tuple(e)}", P1 + e) for e in E] + [(f"P1+2{tuple(e)}", P1 + 2 * e) for e in E]
    return [(name, t, vox.get(tuple(t), 0)) for name, t in out]

def report(offset):
    cl = []
    for i, (name, t, expect) in enumerate(tests()):
        c = (t - offset + 0.25).astype(float).tolist()
        cl.append({"id": i, "kind": "suspect_join", "n_pairs": 0, "n_patches": 0, "area_cm2": 0.0,
                   "centroid_zyx": c, "bbox_zyx": [(t - offset).tolist(), (t - offset).tolist()],
                   "theta_deg": 0.0, "wrap_index_range": [0, 0], "patches": [], "pairs": [], "max_risk": None,
                   "probe_name": name, "probe_expect": expect, "probe_voxel_scan_zyx": t.tolist()})
    return {"contract": "v1", "git": "probe", "branch": "<branch> (placement probe)",
            "region": {"origin_zyx": [0, 0, 0], "shape_zyx": list(SCAN)}, "inputs": {},
            "counts": {"pairs_flagged": 0}, "clusters": cl}

def ome(name, shape_scale, translation=None):
    ds = {"path": "0", "coordinateTransformations": [{"type": "scale", "scale": [VS] * 3}]}
    if translation is not None:
        ds["coordinateTransformations"].append({"type": "translation", "translation": translation})
    return {"multiscales": [{"version": "0.4", "name": name,
                             "axes": [{"name": a, "type": "space", "unit": "micrometer"} for a in "zyx"],
                             "datasets": [ds]}]}

def write(root, shape, fmt, vox_offset, translation, uuid):
    if os.path.exists(root): shutil.rmtree(root)
    g = zarr.open_group(root, mode="w", zarr_format=fmt)
    kw = dict(name="0", shape=shape, chunks=(128, 128, 128), dtype="uint8", fill_value=0, compressors=None)
    if fmt == 2:
        kw["chunk_key_encoding"] = {"name": "v2", "separator": "/"}
    a = g.create_array(**kw)
    for t, v in voxels().items():
        z, y, x = np.array(t) - vox_offset
        a[z, y, x] = v
    g.attrs.update(ome("placement probe", shape, translation))
    json.dump({"type": "vol", "uuid": uuid, "name": uuid, "format": "zarr", "width": shape[2], "height": shape[1],
               "slices": shape[0], "voxelsize": VS}, open(os.path.join(root, "meta.json"), "w"))
    chunks = sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs
                    if not f.startswith(".") and f not in ("zarr.json", "meta.json"))
    return chunks

out = sys.argv[1]
summary = {}
for variant, fmt in (("v2", 2), ("v3", 3)):
    d = os.path.join(out, variant); os.makedirs(d, exist_ok=True)
    summary[variant] = write(os.path.join(d, "overlay_vc3d.zarr"), SCAN, fmt, np.zeros(3, int), None, "probe_" + variant)
    json.dump(report(np.zeros(3, int)), open(os.path.join(d, "report.json"), "w"), indent=1)
d = os.path.join(out, "region"); os.makedirs(d, exist_ok=True)
summary["region"] = write(os.path.join(d, "overlay.zarr"), RSHAPE, 2, ORIGIN, (ORIGIN * VS).tolist(), "probe_region")
# In the region variant the clusters point at voxel - origin: where VC3D draws it if it ignores the translation.
json.dump(report(ORIGIN), open(os.path.join(d, "report.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in summary.items()}, indent=1))
