"""SessB-3: build a villa Spiral dataset root on node-local scratch (runs inside villa_spiral.sif; stdlib + numpy only).

verified_patches/<id>/{x,y,z}.tif + meta.json are extracted byte-for-byte from Stevens' public zips
(s4_good_patches.zip / s4_bad_patches.zip: member s4_<label>_patches/patch_<id>/...), folder name = patch id, which is
what villa's between_patches__A__B resolution requires (SessE-8, SessB). Role files and umbilicus are copied unchanged.
Checks (exit 2 on failure): every between_patches id named in a role file has a folder; umbilicus covers [z0, z1).
Usage: python make_dataset.py --zips DIR --out DIR --umbilicus FILE [--roles DIR] [--ids FILE] --z0 N --z1 N
"""
import argparse, json, os, re, sys, time, zipfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--zips", required=True); ap.add_argument("--out", required=True); ap.add_argument("--umbilicus", required=True)
ap.add_argument("--roles", default=None, help="dir with same_windings.json / relative_windings.json (omit for no constraints)")
ap.add_argument("--ids", default=None, help="file with one patch id per line (omit for every patch in the zips)")
ap.add_argument("--z0", type=int, required=True); ap.add_argument("--z1", type=int, required=True)
a = ap.parse_args(); t0 = time.time(); out = Path(a.out); vp = out / "verified_patches"; vp.mkdir(parents=True, exist_ok=True)
want = None if a.ids is None else {int(x) for x in open(a.ids).read().split()}
n = 0
for lab in ("good", "bad"):
    z = zipfile.ZipFile(Path(a.zips) / f"s4_{lab}_patches.zip")
    for m in z.infolist():
        g = re.match(rf"s4_{lab}_patches/patch_(\d+)/(x\.tif|y\.tif|z\.tif|meta\.json)$", m.filename)
        if not g or (want is not None and int(g.group(1)) not in want):
            continue
        d = vp / g.group(1); d.mkdir(exist_ok=True)
        with z.open(m) as src, open(d / g.group(2), "wb") as dst:
            dst.write(src.read())
        n += g.group(2) == "meta.json"
folders = {p.name for p in vp.iterdir()}
if want is not None and len(folders) != len(want):
    sys.exit(f"FAIL: {len(want)} ids requested, {len(folders)} extracted")
umb = json.load(open(a.umbilicus)); zs = [float(p["z"]) for p in umb["control_points"]]
if min(zs) > a.z0 or max(zs) < a.z1 - 1:
    sys.exit(f"FAIL: umbilicus z {min(zs)}..{max(zs)} does not cover [{a.z0}, {a.z1})")
(out / "umbilicus.json").write_text(json.dumps(umb))
(out / "spiral-scroll.json").write_text(json.dumps({"schema_version": 1, "name": "PHerc1667", "voxel_size_um": 7.91, "spiral_outward_sense": "CW"}))
roles = {}
if a.roles:
    for fn in ("same_windings.json", "relative_windings.json"):
        f = Path(a.roles) / fn
        if not f.exists():
            continue
        doc = json.load(open(f)); missing = set()
        for c in doc["collections"].values():
            nm = c.get("name", "")
            if nm.startswith("between_patches__"):
                missing |= set(nm.split("__")[1:3]) - folders
        if missing:
            sys.exit(f"FAIL: {fn} names {len(missing)} patch ids with no folder (villa would silently re-link), e.g. {sorted(missing)[:5]}")
        (out / fn).write_bytes(f.read_bytes()); roles[fn] = len(doc["collections"])
print(json.dumps(dict(patches=len(folders), roles=roles, z=[a.z0, a.z1], seconds=round(time.time() - t0, 1))))
