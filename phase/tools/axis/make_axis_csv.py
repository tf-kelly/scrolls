#!/usr/bin/env python3
"""Write contract §2's reference-free scroll axis (refmesh.build_axis on the X6 node set: area-weighted patch
centroids per 256-voxel z bin, 3-bin smoothing) as an axis file for segment mode (CONTRACT Amendment 5 §A5.3).
Output: pherc1667_x3slab2_axis.csv, columns z,y,x (scan voxels), every 16 voxels over the bins' supported range."""
import csv
import sys
from pathlib import Path

import numpy as np

O = Path(__file__).resolve().parent; R = O.parents[2]
sys.path.insert(0, str(R / "phase/h1"))
from refmesh import build_axis  # noqa: E402

x6 = list(csv.DictReader(open(R / "phase/x6/x6b_pairs.csv")))
nodes = sorted({r["patch_a"] for r in x6} | {r["patch_b"] for r in x6}, key=int)
axis_xy, patches = build_axis(nodes, None)
cz = np.array([float(patches[int(p)]["cz"]) for p in nodes])
z0, z1 = int(np.floor(cz.min() / 256) * 256 + 128), int(np.ceil(cz.max() / 256) * 256 - 128)   # bin centres: no extrapolation
with open(O / "pherc1667_x3slab2_axis.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["z", "y", "x"])
    for z in range(z0, z1 + 1, 16):
        x, y = axis_xy(float(z)); w.writerow([z, round(float(y), 3), round(float(x), 3)])
print(z0, z1)
