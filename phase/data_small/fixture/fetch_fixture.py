#!/usr/bin/env python3
"""Fetch the third-party parts of the integration fixture and verify every file against the hashes shipped in
provenance.json (next to this script). Nothing third-party is shipped in this tree:

  patches.zip   W. Stevens' patch members (no licence file upstream), read with HTTP range requests from his public
                s4_good_patches.zip / s4_bad_patches.zip; each member's sha256 must equal provenance.json
                `patch_members_sha256`. Members keep their upstream names and bytes.
  ct.zarr/0,1   CT chunks of region A (Vesuvius Challenge open data, under its data terms), fetched from the public
                scan; each raw chunk's sha256 must equal provenance.json `ct.chunk_sha256`, and the assembled level 0
                must equal `ct.level0_sha256`. Level 1 is the 2x mean, as built. The zarr metadata (.zarray/.zattrs)
                ships in the tree; only chunk data is written.

    python3 phase/data_small/fixture/fetch_fixture.py [--only patches|ct] [--limit N] [--labels good,bad]
                                                      [--local-zip DIR_OR_ZIP] [--local-ct ZARR] [--out DIR]

--limit N fetches only the first N patches and verifies only the first N CT chunks (a smoke test; patches go to --out,
never over a full fixture; CT is verified but not written).
--local-zip / --local-ct take the bytes from local copies (for example Stevens' zips already downloaded, or an existing
fixture) instead of the network; the same hashes are checked. Exit status 0 only if every requested file verified.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

F = Path(__file__).resolve().parent
sys.path.insert(0, str(F))
import httpzip  # noqa: E402

CH = 128
sha = lambda b: hashlib.sha256(b).hexdigest()


def fetch_patches(prov, out, limit, labels, local_zip):
    want = prov["patch_members_sha256"]                       # member name -> sha256
    names = sorted(want)
    if labels:
        names = [n for n in names if n.split("/")[0] in {f"s4_{l}_patches" for l in labels}]
    if limit:
        pids = sorted({n.split("/")[1] for n in names})[:limit]
        names = [n for n in names if n.split("/")[1] in pids]
    bylab = {}
    for n in names:
        bylab.setdefault(n.split("/")[0][3:-8], []).append(n)   # s4_<label>_patches/... -> label
    ok = bad = 0
    tmp = out / "patches.zip.part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for lab, members in sorted(bylab.items()):
            url = prov["patch_zips"][lab]
            if local_zip:
                p = Path(local_zip); src = p / f"s4_{lab}_patches.zip" if p.is_dir() else p
                zi = zipfile.ZipFile(src); print(f"{lab}: {len(members)} members from {src}")
            else:
                zi = zipfile.ZipFile(httpzip.HTTPRangeFile(url, block=1 << 17)); print(f"{lab}: {len(members)} members from {url}")
            infos = {i.filename: i for i in zi.infolist()}
            for n in members:
                b = zi.read(infos[n]) if n in infos else None
                if b is None or sha(b) != want[n]:
                    bad += 1; print(f"  MISMATCH {n}: {'missing' if b is None else sha(b)}"); continue
                zo.writestr(n, b); ok += 1
    if bad:
        tmp.unlink(); print(f"patches: {ok} ok, {bad} FAILED; nothing written"); return False
    tmp.replace(out / "patches.zip")
    print(f"patches: {ok} members verified (sha256) -> {out / 'patches.zip'}")
    return True


def fetch_ct(prov, out, local_ct, limit=0):
    import zarr
    ct = prov["ct"]; (z0, y0, x0), shp = ct["origin_voxel_zyx"], ct["shape_zyx"]
    vol = np.zeros(shp, "<u2"); bad = 0
    src = zarr.open_array(str(Path(local_ct) / "0"), mode="r") if local_ct else None
    items = sorted(ct["chunk_sha256"].items())
    for key, h in items[:limit] if limit else items:
        _, cz, cy, cx = (int(v) for v in key.split("/"))
        sl = (slice(cz * CH - z0, (cz + 1) * CH - z0), slice(cy * CH - y0, (cy + 1) * CH - y0), slice(cx * CH - x0, (cx + 1) * CH - x0))
        if src is not None:
            b = np.ascontiguousarray(src[sl], "<u2").tobytes()
        else:
            for attempt in range(5):
                try:
                    b = urllib.request.urlopen(f"{ct['source']}/{key}", timeout=120).read(); break
                except Exception:
                    if attempt == 4:
                        raise
        if len(b) != CH ** 3 * 2 or sha(b) != h:
            bad += 1; print(f"  MISMATCH chunk {key}"); continue
        vol[sl] = np.frombuffer(b, "<u2").reshape(CH, CH, CH)
    if limit:
        print(f"ct: smoke test, {limit - bad} of {limit} chunks verified (sha256); nothing written"); return not bad
    if bad or sha(vol.tobytes()) != ct["level0_sha256"]:
        print(f"ct: {bad} chunk mismatches or level-0 hash mismatch; nothing written"); return False
    # write into the shipped metadata (ct.zarr/.zattrs, 0/.zarray, 1/.zarray): chunk data only
    d = out / "ct.zarr"
    if out != F:
        import shutil
        for m in (".zattrs", ".zgroup", "0/.zarray", "0/.zattrs", "1/.zarray", "1/.zattrs"):
            (d / m).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(F / "ct.zarr" / m, d / m)
    zarr.open_array(str(d / "0"), mode="r+")[...] = vol
    s = vol.shape
    l1 = vol.reshape(s[0] // 2, 2, s[1] // 2, 2, s[2] // 2, 2).mean((1, 3, 5)).round().astype("<u2")
    zarr.open_array(str(d / "1"), mode="r+")[...] = l1
    chk = zarr.open_array(str(d / "0"), mode="r")[...]
    okv = sha(np.ascontiguousarray(chk, "<u2").tobytes()) == ct["level0_sha256"]
    print(f"ct: {len(ct['chunk_sha256'])} chunks verified; level 0 re-read {'matches' if okv else 'DOES NOT MATCH'} "
          f"level0_sha256 -> {d}")
    return okv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=("patches", "ct"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--labels", default="")
    ap.add_argument("--local-zip"); ap.add_argument("--local-ct")
    ap.add_argument("--out", default=str(F))
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    if (a.limit or a.labels) and out == F:
        sys.exit("--limit/--labels make a partial fixture: pass --out to another directory")
    prov = json.load(open(F / "provenance.json"))
    ok = True
    if a.only in (None, "patches"):
        ok &= fetch_patches(prov, out, a.limit, [l for l in a.labels.split(",") if l], a.local_zip)
    if a.only in (None, "ct"):
        ok &= fetch_ct(prov, out, a.local_ct, a.limit)
    print("FETCH OK" if ok else "FETCH FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
