"""Stage 2, export: a villa Spiral dataset root from the check stage, label-free.
  verified_patches/<id>/   tifxyz of every patch in a non-coincident pair, byte-for-byte from the input zip(s)/dir(s)
  same_windings.json, relative_windings.json   one 2-point collection per sampled point pair (points_labelfree.npz),
      dphys = k_b - k_a - s * cross(thN_a, thN_b) from OUR wrap index (arm (a) of SessB / SessF), written by SessE's UNMODIFIED
      convert.write_points; then SessE's snap_anchors.py, loader_filter.py (rule L, rule T') and name_check.py (ties mode),
      unmodified, run from a private copy of phase/sc so their result files do not touch the repository
  umbilicus.json   villa's {"control_points": [{z, y, x}]} from the axis file (every 16 L0 voxels; SessA-12's rule)
  spiral-scroll.json   the scroll's name, voxel size and outward sense, set explicitly by the caller (`scroll`), each
      with its source recorded in EXPORT_MANIFEST.json; the outward sense, if not given, is CW derived from the solve's
      s = +1 (SessE-2) only when the handedness objectives differ; a tie or s = -1 is refused (CONTRACT A18.3)
No reference or label is read: the anchors are our own witness points, not the reference's evaluated pairs."""
import hashlib, importlib.util, json, re, shutil, subprocess, sys, zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
MEMBER = re.compile(r"(?:.*/)?patch_(\d+)/(x\.tif|y\.tif|z\.tif|meta\.json|mask\.tif)$")


def cross(t1, t2):
    e = t1 + (np.mod(t2 - t1 + np.pi, 2 * np.pi) - np.pi)
    return np.where(e >= 2 * np.pi, 1, np.where(e < 0, -1, 0))


def export_patches(sources, ids, dest):
    """Copy patch_<id>/{x,y,z}.tif, meta.json (and mask.tif) for the wanted ids into dest/<id>/."""
    dest.mkdir(parents=True, exist_ok=True); got = set()
    for s in map(Path, sources):
        if s.is_dir():
            for d in s.rglob("patch_*"):
                m = re.match(r"patch_(\d+)$", d.name)
                if m and int(m.group(1)) in ids and d.is_dir():
                    shutil.copytree(d, dest / m.group(1), dirs_exist_ok=True); got.add(int(m.group(1)))
        else:
            with zipfile.ZipFile(s) as z:
                for n in z.namelist():
                    m = MEMBER.match(n)
                    if m and int(m.group(1)) in ids:
                        (dest / m.group(1)).mkdir(exist_ok=True); (dest / m.group(1) / m.group(2)).write_bytes(z.read(n)); got.add(int(m.group(1)))
    missing = sorted(set(ids) - got)
    if missing:
        raise SystemExit(f"export: {len(missing)} patches not found in the inputs, e.g. {missing[:5]}")
    return len(got)


def umbilicus(axis_file, path):
    ax = np.loadtxt(axis_file, delimiter=","); zs = np.arange(0, ax[-1, 0] + 1, 16, dtype=float)
    ay, axx = np.interp(zs, ax[:, 0], ax[:, 1]), np.interp(zs, ax[:, 0], ax[:, 2])
    path.write_text(json.dumps({"control_points": [{"z": float(z), "y": round(float(y), 3), "x": round(float(x), 3)} for z, y, x in zip(zs, ay, axx)]}, indent=1) + "\n")
    err = float(np.max(np.hypot(np.interp(ax[:, 0], zs, np.round(ay, 3)) - ax[:, 1], np.interp(ax[:, 0], zs, np.round(axx, 3)) - ax[:, 2])))
    return dict(n_control_points=len(zs), max_abs_error_vox=err)


def run_export(out, repo, patches, axis_file, zrange, villa=None, python=None, scroll=None):
    """scroll: dict(name, voxel_size_um, spiral_outward_sense or None, source={field: where the value came from})."""
    chk, run, ds = out / "check", out / "run", out / "dataset"
    sc = out / "_sc/phase/sc"                                     # private copy: SessE's scripts write their stats under phase/sc/results
    if sc.exists():
        shutil.rmtree(sc)
    shutil.copytree(repo / "phase/sc", sc, ignore=shutil.ignore_patterns("fixture", "results", "__pycache__")); (sc / "results").mkdir()
    spec = importlib.util.spec_from_file_location("sc_convert", sc / "convert.py"); conv = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(sc)); spec.loader.exec_module(conv)
    P = np.load(run / "points_labelfree.npz"); EP, pair = P["edge_patches"], P["edge"]
    wi = pd.read_csv(chk / "wrap_index.csv").set_index("patch"); s = int(json.load(open(chk / "wrap_index.json"))["s_chosen"])
    if s != 1:
        raise SystemExit("export: the solve chose s = -1; CW (villa's spiral_outward_sense) is derived from s = +1 (SessE-2), so no dataset is written")
    a, b = EP[pair, 0], EP[pair, 1]; ka, kb = wi.k_q3c.reindex(a).values, wi.k_q3c.reindex(b).values
    ok = np.isfinite(ka) & np.isfinite(kb); cut = np.zeros(len(a), int)
    cut[ok] = cross(wi.thN.reindex(a).values[ok], wi.thN.reindex(b).values[ok])
    PA, PB = P["PA"].astype(float), P["PB"].astype(float)
    df = pd.DataFrame(dict(a=a, b=b, dphys=kb - ka - s * cut, ax=PA[:, 0], ay=PA[:, 1], az=PA[:, 2], bx=PB[:, 0], by=PB[:, 1], bz=PB[:, 2], pair=pair))[ok]
    df["dphys"] = df.dphys.astype(int)
    ids = sorted(set(df.a) | set(df.b))
    n = export_patches(patches, set(int(i) for i in ids), ds / "verified_patches")
    umb = umbilicus(axis_file, ds / "umbilicus.json")
    if not scroll or not scroll.get("name") or not scroll.get("voxel_size_um"):
        raise SystemExit("export: the scroll's name and voxel size must be given explicitly (--scroll-name, --voxel-um)")
    src = dict(scroll.get("source") or {})
    sense = scroll.get("spiral_outward_sense")
    if sense is None:
        obj = json.load(open(chk / "wrap_index.json")).get("objectives") or {}
        o_pos, o_neg = obj.get("1", obj.get(1)), obj.get("-1", obj.get(-1))
        if o_pos is None or o_neg is None or float(o_pos) == float(o_neg):   # CONTRACT A18.3: a tie is not a handedness
            raise SystemExit(f"export: handedness is not identifiable on this set (objectives s=+1 {o_pos}, s=-1 {o_neg}); "
                             "pass --outward-sense CW|ACW with its source (e.g. villa's catalogue rule)")
        sense, src["spiral_outward_sense"] = "CW", (f"derived: the solve chose s = +1 (objectives {o_pos} vs {o_neg}), "
                                                    "which maps to villa's CW (SessE-2)")
    spec = {"schema_version": 1, "name": str(scroll["name"]), "voxel_size_um": float(scroll["voxel_size_um"]), "spiral_outward_sense": str(sense).upper()}
    (ds / "spiral-scroll.json").write_text(json.dumps(spec, indent=1) + "\n")
    env = conv.write_points(df, ds, dict(contract="v1", tool="vc-unwrap", label="arm (a): our solved wrap index, label-free witness anchors",
                                         region=dict(origin_zyx=[int(df[c].min()) for c in ("az", "ay", "ax")], shape_zyx=[int(df[c].max() - df[c].min()) + 1 for c in ("az", "ay", "ax")])))
    for fn in ("same_windings.json", "relative_windings.json"):
        (ds / fn).write_bytes((ds / "spiral" / fn).read_bytes())
    man = dict(patches=n, point_pairs=int(len(df)), dropped_no_index=int((~ok).sum()), s_chosen=s, z_range=list(zrange),
               dphys_counts={str(v): int(c) for v, c in df.dphys.value_counts().sort_index().items()}, prefilter=env["constraints"], umbilicus=umb,
               scroll_spec=dict(spec, source=src))
    py = python or sys.executable                                 # villa's loader and name check need villa's dependencies
    r = subprocess.run([py, str(sc / "sc8/snap_anchors.py"), str(ds)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("export: snap_anchors.py failed\n" + r.stderr[-2000:])
    man["snap"] = json.load(open(sc / "results/sc8_snap.json"))
    if villa is None:
        man["loader_filter"] = man["name_check"] = "not run: no --villa given (the fit stage needs both; run export with --villa)"
    else:
        r = subprocess.run([py, str(sc / "sc8/loader_filter.py"), str(villa), str(zrange[0]), str(zrange[1]), str(ds)], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("export: loader_filter.py failed\n" + r.stderr[-3000:])
        man["loader_filter"] = json.load(open(sc / "results/sc8c_loader_filter.json"))
        o = out / "name_check.json"
        r = subprocess.run([py, str(sc / "sc8/name_check.py"), str(villa), str(ds), str(o), str(zrange[0]), str(zrange[1]), "--allow-same-winding-ties"], capture_output=True, text=True)
        man["name_check"] = dict(exit=r.returncode, passed=r.returncode == 0, file=o.name, tail=(r.stdout + r.stderr)[-600:])
        if r.returncode:
            raise SystemExit("export: villa's own loader links some constraint to the wrong patch (name_check.json); no fit on this dataset")
    man["files"] = {str(p.relative_to(ds)): sha(p) for p in sorted(ds.rglob("*")) if p.is_file() and "verified_patches" not in p.parts}
    (out / "EXPORT_MANIFEST.json").write_text(json.dumps(man, indent=1, default=str) + "\n")
    return man
