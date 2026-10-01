"""Write a VC3D-loadable view of a region zarr that carries an OME translation.

SUPERSEDED for overlays by contract Amendment 4 (the CLI writes overlay.zarr full-frame natively). Still used
by the in-app tests to open the fixture's ct.zarr (a v1 file with a translation) as VC3D's base volume.

VC3D (villa f4570bf, core/src/render/ZarrChunkFetcher.cpp:757) rejects any OME
`translation` that is not zero. Contract v1 §4.2 requires translation = region
origin x 7.91 um. This script writes `<dst>` with:
  - level 0 only, shape = the full scan shape, zero translation, same chunks,
    dtype, compressor and dimension_separator as the source level 0;
  - each source chunk file copied byte-for-byte to its scan-frame key
    (chunk index + origin / chunk). Nothing is decoded or resampled.
  - a VC3D meta.json (type vol, width/height/slices = scan x/y/z).
It requires the region origin to be a multiple of the chunk size at level 0,
which §4.2 guarantees (128). Coarser levels are not relocatable this way
(origin / 2^l is generally not chunk-aligned) and are omitted.

Usage: overlay_vc3d_view.py SRC.zarr DST.zarr --scan-shape Z Y X [--uuid ID] [--name NAME]
The region origin is read from SRC/.zattrs (translation / scale).
"""
import argparse, json, os, shutil, sys


def region_origin(src):
    attrs = json.load(open(os.path.join(src, ".zattrs")))
    ds = attrs["multiscales"][0]["datasets"][0]
    assert ds["path"] == "0", "first multiscales dataset must be level 0"
    scale, trans = [1.0] * 3, [0.0] * 3
    for t in ds.get("coordinateTransformations", []):
        if t["type"] == "scale":
            scale = t["scale"]
        elif t["type"] == "translation":
            trans = t["translation"]
    origin = [trans[i] / scale[i] for i in range(3)]
    rounded = [int(round(o)) for o in origin]
    assert all(abs(o - r) < 1e-3 for o, r in zip(origin, rounded)), f"non-integer origin {origin}"
    return rounded, scale


def write_view(src, dst, scan_shape, uuid, name):
    origin, scale = region_origin(src)
    zarray = json.load(open(os.path.join(src, "0", ".zarray")))
    chunks, sep = zarray["chunks"], zarray.get("dimension_separator", ".")
    shape = zarray["shape"]
    for i in range(3):
        if origin[i] % chunks[i]:
            raise SystemExit(f"origin {origin} not aligned to chunks {chunks}")
        if origin[i] + shape[i] > scan_shape[i]:
            raise SystemExit(f"region {origin}+{shape} exceeds scan shape {scan_shape}")
    off = [origin[i] // chunks[i] for i in range(3)]
    if os.path.exists(dst):
        shutil.rmtree(dst)
    lvl = os.path.join(dst, "0")
    os.makedirs(lvl)
    json.dump({"zarr_format": 2}, open(os.path.join(dst, ".zgroup"), "w"))
    json.dump({"multiscales": [{
        "version": "0.4", "name": name,
        "axes": [{"name": a, "type": "space", "unit": "micrometer"} for a in "zyx"],
        "datasets": [{"path": "0", "coordinateTransformations": [{"type": "scale", "scale": list(scale)}]}]}],
        "vc3d_view_of": {"source": os.path.abspath(src), "origin_zyx": origin}},
        open(os.path.join(dst, ".zattrs"), "w"), indent=1)
    view = dict(zarray, shape=list(scan_shape))
    json.dump(view, open(os.path.join(lvl, ".zarray"), "w"), indent=1)
    n = 0
    src0 = os.path.join(src, "0")
    for root, _, files in os.walk(src0):
        for f in files:
            if f.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(root, f), src0)
            idx = [int(p) for p in (rel.split(os.sep) if sep == "/" else rel.split("."))]
            new = [idx[i] + off[i] for i in range(3)]
            key = os.path.join(*map(str, new)) if sep == "/" else ".".join(map(str, new))
            out = os.path.join(lvl, key)
            os.makedirs(os.path.dirname(out) or lvl, exist_ok=True)
            shutil.copyfile(os.path.join(root, f), out)
            n += 1
    json.dump({"type": "vol", "uuid": uuid, "name": name, "format": "zarr",
               "width": scan_shape[2], "height": scan_shape[1], "slices": scan_shape[0],
               "voxelsize": float(scale[0])}, open(os.path.join(dst, "meta.json"), "w"), indent=1)
    return {"origin_zyx": origin, "chunk_offset": off, "chunks_copied": n}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--scan-shape", nargs=3, type=int, required=True, metavar=("Z", "Y", "X"))
    ap.add_argument("--uuid", default=None); ap.add_argument("--name", default="sheet check overlay")
    a = ap.parse_args(argv)
    uuid = a.uuid or "sheet_check_" + os.path.basename(os.path.dirname(os.path.abspath(a.dst)))
    print(json.dumps(write_view(a.src, a.dst, a.scan_shape, uuid, a.name)))


if __name__ == "__main__":
    main()
