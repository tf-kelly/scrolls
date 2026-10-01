"""Mesh input/output: tifxyz grids and OBJ triangle meshes.

Both are reduced to one internal form, a `Mesh`:
  xyz    (N, 3) float64, L0 voxel coordinates in x, y, z order (VC convention)
  valid  (N,) bool
  edges  (E, 2) int, undirected mesh edges between valid vertices
  grid   (H, W) int index into xyz for tifxyz input, else None
  faces  (F, 3) int for OBJ input, else None

tifxyz: a directory holding x.tif, y.tif, z.tif (float32, H x W) and usually
meta.json. Holes are -1 (VC3D writes -1; the S1b loader also treated any
non-positive x or z, or a non-finite value, as a hole -- kept here).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Mesh:
    xyz: np.ndarray
    valid: np.ndarray
    edges: np.ndarray
    kind: str
    source: str
    grid: np.ndarray | None = None
    faces: np.ndarray | None = None
    meta: dict = field(default_factory=dict)

    @property
    def shape(self):
        return None if self.grid is None else self.grid.shape

    def bbox(self):
        v = self.xyz[self.valid]
        return v.min(0), v.max(0)


def _grid_edges(H, W, ok):
    idx = np.arange(H * W).reshape(H, W)
    e = []
    for a, b in ((idx[:, :-1], idx[:, 1:]), (idx[:-1, :], idx[1:, :])):
        oa = ok[a.ravel()]; ob = ok[b.ravel()]
        k = oa & ob
        e.append(np.stack([a.ravel()[k], b.ravel()[k]], 1))
    return np.concatenate(e).astype(np.int64)


def read_tifxyz(path) -> Mesh:
    import tifffile
    path = Path(path)
    g = np.stack([tifffile.imread(path / f"{c}.tif").astype(np.float64) for c in "xyz"], -1)
    H, W = g.shape[:2]
    ok = np.isfinite(g).all(-1) & (g[..., 0] > 0) & (g[..., 2] > 0) & ~(g == -1).any(-1)
    meta = {}
    if (path / "meta.json").exists():
        meta = json.loads((path / "meta.json").read_text())
    xyz = g.reshape(-1, 3)
    okf = ok.ravel()
    return Mesh(xyz=xyz, valid=okf, edges=_grid_edges(H, W, okf), kind="tifxyz", source=str(path),
                grid=np.arange(H * W).reshape(H, W), meta=meta)


def read_obj(path) -> Mesh:
    """Vertices ('v x y z') and faces ('f a/b/c ...', 1-based, polygons fanned to triangles)."""
    vs, fs = [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                vs.append([float(t) for t in line.split()[1:4]])
            elif line.startswith("f "):
                ids = [int(t.split("/")[0]) for t in line.split()[1:]]
                ids = [i - 1 if i > 0 else len(vs) + i for i in ids]
                for k in range(1, len(ids) - 1):
                    fs.append([ids[0], ids[k], ids[k + 1]])
    xyz = np.asarray(vs, np.float64).reshape(-1, 3)
    faces = np.asarray(fs, np.int64).reshape(-1, 3)
    ok = np.isfinite(xyz).all(1)
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.sort(e, 1); e = np.unique(e, axis=0)
    e = e[ok[e[:, 0]] & ok[e[:, 1]]]
    return Mesh(xyz=xyz, valid=ok, edges=e, kind="obj", source=str(path), faces=faces)


def read_mesh(path) -> Mesh:
    p = Path(path)
    if p.is_dir() and (p / "x.tif").exists():
        return read_tifxyz(p)
    if p.suffix.lower() == ".obj":
        return read_obj(p)
    raise ValueError(f"not a tifxyz directory (x.tif, y.tif, z.tif) or .obj file: {p}")


def write_tifxyz(path, mesh: Mesh, keep: np.ndarray, extra_meta: dict | None = None):
    """Write the grid with vertices where keep is False set to -1 (VC3D's hole
    value). Only defined for tifxyz input: an OBJ has no grid to write."""
    import tifffile
    if mesh.grid is None:
        raise ValueError("cleaned tifxyz output needs tifxyz input")
    path = Path(path); path.mkdir(parents=True, exist_ok=True)
    H, W = mesh.grid.shape
    g = mesh.xyz.reshape(H, W, 3).astype(np.float32).copy()
    drop = ~(keep & mesh.valid).reshape(H, W)
    g[drop] = -1.0
    for i, c in enumerate("xyz"):
        tifffile.imwrite(path / f"{c}.tif", g[..., i])
    meta = dict(mesh.meta)
    if extra_meta:
        meta.update(extra_meta)
    v = g[~drop]
    if len(v):
        meta["bbox"] = [v.min(0).tolist(), v.max(0).tolist()]
    (path / "meta.json").write_text(json.dumps(meta, indent=1))
