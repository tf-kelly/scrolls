"""FLATTEN: whole fitted surface of a Spiral checkpoint -> combined tifxyz -> lasagna flatten.

Uses villa's flatten_spiral_checkpoint unchanged (its _checkpoint_config,
_export_source_surface, _resolve_lasagna and _flatten, i.e. the lasagna fit_service flatten
with configs/flatten_fast_nofilter.json). Differences from its CLI, both recorded in
flatten.json:
  * the winding range: villa's CLI exports windings [preview_first_winding or 10,
    shell_outer_winding_idx (130)]; here the range can be set, by default from PLACE's snapped
    winding range (min-1 .. max+1, capped at the allocated capacity - 1), so the whole fitted
    surface that carries patches is exported;
  * the unflattened source surface is kept (source/), and the flattened one is trimmed to its
    valid-cell bounding box in numpy (what vc_tifxyz_trim does).

Run from villa/spiral-fitting:
  python -m vc_scale.flatten --ckpt CKPT --umbilicus U --lasagna-dir L --out OUT [--place-json P]
"""
import argparse
import gc
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np


def trim_tifxyz(path):
    """Crop a tifxyz (x/y/z.tif, optional other same-size tifs) to its valid-cell bbox."""
    import tifffile
    p = Path(path)
    x = tifffile.imread(p / 'x.tif')
    v = x != -1
    if not v.any():
        return None
    r = np.nonzero(v.any(1))[0]
    c = np.nonzero(v.any(0))[0]
    sl = np.s_[r[0]:r[-1] + 1, c[0]:c[-1] + 1]
    H, W = x.shape
    for f in p.glob('*.tif'):
        a = tifffile.imread(f)
        if a.shape[:2] == (H, W):
            tifffile.imwrite(f, np.ascontiguousarray(a[sl]), compression='zlib')
    meta = json.loads((p / 'meta.json').read_text())
    xyz = [tifffile.imread(p / f'{n}.tif') for n in 'xyz']
    vv = xyz[0] != -1
    meta['bbox'] = [[float(a[vv].min()) for a in xyz], [float(a[vv].max()) for a in xyz]]
    (p / 'meta.json').write_text(json.dumps(meta, indent=1))
    return dict(rows=[int(r[0]), int(r[-1]) + 1], cols=[int(c[0]), int(c[-1]) + 1], from_shape=[H, W])


def main(argv=None):
    import torch
    import flatten_spiral_checkpoint as fsc
    from checkpoint_io import load_checkpoint_cpu
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ckpt', default='')
    ap.add_argument('--umbilicus', default='')
    ap.add_argument('--lasagna-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--voxel-um', type=float, default=7.91)
    ap.add_argument('--first', type=int, default=None)
    ap.add_argument('--last', type=int, default=None)
    ap.add_argument('--place-json', default='')
    ap.add_argument('--chunk-size', type=int, default=65536)
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--skip-flatten', action='store_true', help='export the source surface only')
    ap.add_argument('--surface', default='', help='flatten this existing tifxyz instead of exporting the checkpoint')
    a = ap.parse_args(argv)
    t0 = time.time()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rec = dict(ckpt=os.path.abspath(a.ckpt), umbilicus=os.path.abspath(a.umbilicus), voxel_um=a.voxel_um)
    device = torch.device(a.device)
    if a.surface:   # flatten a given tifxyz (e.g. the quilt), no checkpoint export
        service, fcfg = fsc._resolve_lasagna(Path(a.lasagna_dir))
        flat = out / 'flat.tifxyz'
        if flat.exists():
            shutil.rmtree(flat)
        work = Path(tempfile.mkdtemp(prefix='.flatten-', dir=str(out)))
        t1 = time.time()
        try:
            fsc._flatten(Path(a.surface).resolve(), flat, service, fcfg, work, voxel_size_um=a.voxel_um)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        rec = dict(surface=os.path.abspath(a.surface), flatten_s=round(time.time() - t1, 1), lasagna_config=str(fcfg),
                   trim=trim_tifxyz(flat), flat_surface=str(flat), voxel_um=a.voxel_um)
        import tifffile
        x = tifffile.imread(flat / 'x.tif')
        rec.update(flat_surface_shape=list(x.shape), flat_surface_valid_cells=int((x != -1).sum()),
                   wall_s=round(time.time() - t0, 1))
        json.dump(rec, open(out / 'flatten.json', 'w'), indent=1)
        print(json.dumps(rec), flush=True)
        return
    ckpt = load_checkpoint_cpu(a.ckpt)
    config = fsc._checkpoint_config(ckpt)
    cap = int(config.get('model_gap_expander_capacity_windings',
                         config.get('model_gap_expander_num_windings', 144)))
    villa_first = int(ckpt.get('preview_first_winding', fsc._value(config, 'first_winding', 10)))
    villa_last = config.get('shell_outer_winding_idx')
    villa_last = int(villa_last) if villa_last is not None else int(config['model_gap_expander_num_windings']) - 1
    first, last = villa_first, villa_last
    if a.place_json and os.path.exists(a.place_json):
        pj = json.load(open(a.place_json))
        rng = pj.get('snapped_winding_range')
        if rng:
            first, last = max(0, rng[0] - 1), min(cap - 1, rng[1] + 1)
            rec['range_source'] = f'PLACE snapped winding range {rng} (+-1)'
    if a.first is not None:
        first = a.first
    if a.last is not None:
        last = a.last
    rec.update(villa_default_range=[villa_first, villa_last], capacity=cap, exported_range=[first, last])
    ckpt['preview_first_winding'] = first
    config['shell_outer_winding_idx'] = last
    print(f'[scale] windings {first}..{last} (villa default {villa_first}..{villa_last}, capacity {cap})', flush=True)

    src_dir = out / 'source'
    if src_dir.exists():
        shutil.rmtree(src_dir)
    t1 = time.time()
    surface = fsc._export_source_surface(ckpt, config, Path(a.umbilicus).resolve(), src_dir, device=device,
                                         voxel_size_um=a.voxel_um, chunk_size=a.chunk_size)
    rec['source_surface'] = str(surface)
    rec['export_s'] = round(time.time() - t1, 1)
    man = src_dir / 'manifest.json'
    if not man.exists():
        cands = list(src_dir.rglob('manifest.json'))
        man = cands[0] if cands else None
    if man:
        rec['source_manifest'] = str(man)
    del ckpt
    gc.collect()
    if device.type == 'cuda':
        torch.cuda.empty_cache()
    if not a.skip_flatten:
        service, fcfg = fsc._resolve_lasagna(Path(a.lasagna_dir))
        flat = out / 'flat.tifxyz'
        if flat.exists():
            shutil.rmtree(flat)
        work = Path(tempfile.mkdtemp(prefix='.flatten-', dir=str(out)))
        t1 = time.time()
        try:
            fsc._flatten(surface, flat, service, fcfg, work, voxel_size_um=a.voxel_um)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        rec['flatten_s'] = round(time.time() - t1, 1)
        rec['lasagna_config'] = str(fcfg)
        rec['trim'] = trim_tifxyz(flat)
        rec['flat_surface'] = str(flat)
    import tifffile
    for key in ('source_surface', 'flat_surface'):
        if key in rec:
            x = tifffile.imread(Path(rec[key]) / 'x.tif')
            rec[key + '_shape'] = list(x.shape)
            rec[key + '_valid_cells'] = int((x != -1).sum())
    rec['wall_s'] = round(time.time() - t0, 1)
    if device.type == 'cuda':
        rec['cuda_max_allocated_gb'] = round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)
    json.dump(rec, open(out / 'flatten.json', 'w'), indent=1)
    print(json.dumps(rec), flush=True)


if __name__ == '__main__':
    main()
