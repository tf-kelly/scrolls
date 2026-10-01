"""Fixture CT region A as a VC3D-friendly base volume: uint8, full scan frame, levels 0 and 1, translation 0.

Usage: make_ct_u8.py OUT.zarr   (zarr==2.18.7)
Why: VC3D f4570bf draws uint16 volumes as noise (PR.md Draft 3), so controls need uint8 CT to be visible; SessA's segment
mode reads level 1 (segment.py LEVEL = 1), so the plugin's --volume needs levels 0 and 1; VC3D ignores OME translations
(A10.1), so it must be full-frame.
Mapping: uint8 = round(clip((v - lo) / (hi - lo), 0, 1) * 255) with lo/hi = level-0 p0.5 / p99.8 of the region,
applied to level 0 and to the fixture's own level 1 (a 2x mean over {2a, 2a+1}, build_fixture.py:57). Recorded in
meta.json "u8_mapping".
"""
import json, os, shutil, sys
import numpy as np, zarr
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 4))
SRC = os.path.join(REPO, "phase/data_small/fixture/ct.zarr")
SCAN = (11174, 3340, 3440); VS = 7.91; O0 = np.array([4224, 2560, 640])
out = sys.argv[1]
# Optional: --plant AZ AY AX plants a distinctive CT feature, value 255 at level-0 voxels [2a, 2a+1]^3 and so 255 at
# level-1 voxel a (the 2x mean of 255s), for the relative level-1 check (SessD-5 (2)).
plant = [int(v) for v in sys.argv[sys.argv.index("--plant") + 1:][:3]] if "--plant" in sys.argv else None
src = zarr.open_group(SRC, mode="r")
a0 = src["0"][:].astype(np.float64); a1 = src["1"][:].astype(np.float64)
lo, hi = np.percentile(a0, [0.5, 99.8])
to8 = lambda a: np.round(np.clip((a - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
if os.path.exists(out): shutil.rmtree(out)
g = zarr.open_group(out, mode="w")
u0, u1 = to8(a0), to8(a1)
if plant:
    A = np.array(plant); b0 = 2 * A - O0; b1 = A - O0 // 2
    u0[b0[0]:b0[0] + 2, b0[1]:b0[1] + 2, b0[2]:b0[2] + 2] = 255
    u1[b1[0], b1[1], b1[2]] = 255
for l, a in ((0, u0), (1, u1)):
    shape = tuple(-(-s // 2 ** l) for s in SCAN)
    d = g.create_dataset(str(l), shape=shape, chunks=(128, 128, 128), dtype="uint8", fill_value=0,
                         compressor=zarr.Blosc(cname="lz4", clevel=5, shuffle=1), dimension_separator="/", write_empty_chunks=False)
    o = O0 // 2 ** l
    d[o[0]:o[0] + a.shape[0], o[1]:o[1] + a.shape[1], o[2]:o[2] + a.shape[2]] = a
g.attrs["multiscales"] = [{"version": "0.4", "name": "fixture CT region A, uint8",
    "axes": [{"name": n, "type": "space", "unit": "micrometer"} for n in "zyx"],
    "datasets": [{"path": str(l), "coordinateTransformations": [{"type": "scale", "scale": [VS * 2 ** l] * 3}]} for l in (0, 1)]}]
json.dump({"type": "vol", "uuid": "fixture_ct_A_u8" + ("_planted" if plant else ""), "planted_level1_voxel_zyx": plant, "name": "fixture CT region A (uint8, 2 levels)", "format": "zarr",
           "width": SCAN[2], "height": SCAN[1], "slices": SCAN[0], "voxelsize": VS,
           "u8_mapping": {"lo_uint16": float(lo), "hi_uint16": float(hi), "source": "phase/data_small/fixture/ct.zarr levels 0,1"}},
          open(os.path.join(out, "meta.json"), "w"), indent=1)
print(json.dumps({"lo": lo, "hi": hi, "l0_shape": a0.shape, "l1_shape": a1.shape}))
