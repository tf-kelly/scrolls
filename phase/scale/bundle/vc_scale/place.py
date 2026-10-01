"""PLACE: placed area of the traced patches on a fitted Spiral checkpoint, using villa's own
per-patch satisfaction machinery (satisfaction_metrics.evaluate_patch_satisfaction_packed),
plus the per-pair fitted winding deltas the arbiter needs.

Run from villa/spiral-fitting (its modules import each other as top-level names):

  python -m vc_scale.place arm     --arm NAME --ckpt CKPT --dataset DS --out OUT [--pairs-from DS_WITH_PAIRS]
  python -m vc_scale.place combine --out OUT --arms arm_a arm_b [--run-small arm_a=TGZ ...]

`arm` writes OUT/NAME/: place.json (totals per tolerance, per regime, unique area, winding
range), quads.npz (packed per-quad bits aligned to villa's packed quad order), pairs.npz (fitted
w at both points of every same/relative pair), quad_cn.npy (quad centres and normals, for the
picture's support map).
`combine` writes OUT/place_summary.json and OUT/place_table.md: arm tables, the a-b gap by
regime, arm disagreements, the arbiter, and the 6-voxel cross-check against the fit's own
satisfied_fitted.json.

A quad is "placed at tolerance t" when villa marks it satisfied with
satisfaction_distance_tolerance = t voxels (its centre lies within t voxels of the fitted surface
of the integer winding it snaps to; villa's spiral-space 0.45*dr test also applies). That is
geometric agreement, not winding identity.
"""
import argparse
import json
import os
import sys
import tarfile
import time

import numpy as np

REGIMES = ('<25', '25-50', '>=50', 'none')
UCELL = 20.0    # vox, unique-area cell


def _log(*a):
    print(f'[{time.strftime("%H:%M:%S")}]', *a, flush=True)


def _load_context(ckpt_path, dataset):
    import torch
    import fit_spiral as fs
    import find_inconsistent_windings as fiw
    from checkpoint_io import load_checkpoint_cpu
    from fit_session import conventional_input_paths, load_scroll_spec
    torch.set_grad_enabled(False)
    ckpt = load_checkpoint_cpu(ckpt_path)
    spec = load_scroll_spec(dataset, None)
    paths = conventional_input_paths(dataset, spec)
    fit_cfg, scroll, in_paths, zb, ze = fiw.build_fit_inputs(
        ckpt, paths.verified_patches, [], ckpt['z_begin'], ckpt['z_end'], paths.umbilicus)
    ctx = fs.FitContext(fit_cfg, scroll=scroll, paths=in_paths)
    ctx.load_host_inputs()
    transform, dr = fiw.build_transform(ckpt, fit_cfg, ctx, zb, ze)
    cfg = fs.Config().as_dict()
    cfg.update(ckpt['cfg'])
    return ckpt, ctx, transform, dr, zb, ze, cfg, paths


def _quad_geometry(atlas, corners, batch=1 << 22):
    """Quad centres (N,3), unit normals (N,3) and 3-D quad areas (N,) in vox^2 from villa's atlas."""
    import torch
    n = len(corners)
    cen = np.empty((n, 3), np.float32)
    nrm = np.empty((n, 3), np.float32)
    area = np.empty(n, np.float32)
    for b in range(0, n, batch):
        v = atlas.vertex_zyxs(corners[b:b + batch].to(atlas.device))   # (B,4,3): corner order as villa packs it
        c = v.mean(1)
        # quad corners as packed: use both diagonals (0-2, 1-3) of whatever cyclic order; area =
        # 0.5 |d1 x d2| is exact for planar quads and order-independent up to diagonal choice,
        # so take the max over the two possible diagonal pairings.
        d1, d2 = v[:, 2] - v[:, 0], v[:, 3] - v[:, 1]
        e1, e2 = v[:, 3] - v[:, 0], v[:, 2] - v[:, 1]
        x1 = torch.cross(d1, d2, dim=-1)
        x2 = torch.cross(e1, e2, dim=-1)
        a1 = 0.5 * torch.linalg.norm(x1, dim=-1)
        a2 = 0.5 * torch.linalg.norm(x2, dim=-1)
        x = torch.where((a1 >= a2)[:, None], x1, x2)
        cen[b:b + batch] = c.cpu().numpy()
        nrm[b:b + batch] = (x / torch.linalg.norm(x, dim=-1, keepdim=True).clamp_min(1e-12)).cpu().numpy()
        area[b:b + batch] = torch.maximum(a1, a2).cpu().numpy()
    return cen, nrm, area


def _regimes(patch_ids, offsets, cen, pairs_by_patch, radius):
    from scipy.spatial import cKDTree
    from .regime import regime_code
    reg = np.full(len(cen), 3, np.int8)
    for i, pid in enumerate(patch_ids):
        anc = pairs_by_patch.get(str(pid))
        b, e = int(offsets[i]), int(offsets[i + 1])
        if anc is None or e <= b:
            continue
        d, j = cKDTree(anc[0]).query(cen[b:e], k=1, distance_upper_bound=radius)
        hit = np.isfinite(d)
        r = np.full(e - b, 3, np.int8)
        r[hit] = regime_code(anc[1][j[hit]])
        reg[b:e] = r
    return reg


def _unique_area_cm2(evaluation, sel, dr, voxel_um):
    """Area of the distinct (snapped winding, z, arc length) cells of UCELL voxels hit by
    the selected quads: overlapping traces of one sheet count once."""
    import torch
    sp = evaluation.center_spiral_zyxs
    th = evaluation.center_theta
    tw = evaluation.target_winding_indices.to(sp.device)
    m = torch.as_tensor(sel, device=sp.device) & (tw >= 0)
    if not bool(m.any()):
        return 0.0, 0
    r = torch.linalg.norm(sp[m][:, 1:], dim=-1)
    zb = torch.floor(sp[m][:, 0] / UCELL).to(torch.int64)
    ab = torch.floor(th[m].to(sp.dtype) * r / UCELL).to(torch.int64)
    key = (tw[m].to(torch.int64) << 42) + ((zb + (1 << 20)) << 21) + (ab + (1 << 20))
    n = int(torch.unique(key).numel())
    return n * UCELL * UCELL * (voxel_um * 1e-4) ** 2, n


def _pairs_w(transform, dr, dataset):
    """Fitted w = shifted_radius/dr at both points of every same/relative pair, plus the theta
    seam adjustment villa's find_inconsistent_windings uses (per point, cumulative)."""
    import torch
    import find_inconsistent_windings as fiw
    from sample_spiral import get_theta_and_radii
    from sample_spiral import unwrap_shifted_radii
    out = {}
    for fn in ('same_windings.json', 'relative_windings.json'):
        f = os.path.join(dataset, fn)
        if not os.path.exists(f):
            continue
        cols = json.load(open(f))['collections']
        P = np.empty((len(cols), 2, 3), np.float32)
        W = np.zeros((len(cols), 2), np.float32)
        for n, c in enumerate(cols.values()):
            pts = sorted(c['points'].items(), key=lambda kv: int(kv[0]))
            for s in range(2):
                P[n, s] = np.asarray(pts[s][1]['p'], np.float32)[::-1]
                W[n, s] = float(pts[s][1].get('wind_a', 0.0) or 0.0)
        w = np.full((len(P), 2), np.nan, np.float32)
        adj = np.zeros((len(P), 2), np.int64)
        flat = torch.as_tensor(P.reshape(-1, 3), device=dr.device)
        wf = np.empty(len(flat), np.float32)
        thf = np.empty(len(flat), np.float32)
        for b in range(0, len(flat), 1 << 18):
            q = flat[b:b + (1 << 18)]
            wf[b:b + len(q)] = fiw.winding_at_points(transform, dr, q).float().cpu().numpy()
            th, _, _ = get_theta_and_radii(transform(q)[..., 1:], dr)
            thf[b:b + len(q)] = th.float().cpu().numpy()
        w[:] = wf.reshape(-1, 2)
        # villa's seam transport between the two points of a pair (as _tour_unwrap_adjustments):
        th2 = torch.as_tensor(thf.reshape(-1, 2), device=dr.device)
        _, a = unwrap_shifted_radii(th2, torch.zeros_like(th2), dr)
        adj[:] = np.round((a / dr).cpu().numpy()).astype(np.int64)
        sep = np.linalg.norm(P[:, 0] - P[:, 1], axis=-1)
        out[fn] = dict(w=w, adj=adj, wind=W, sep_vox=sep)
    return out


def cmd_arm(a):
    import torch
    import satisfaction_metrics as sm
    from .regime import load_relative_pairs
    t0 = time.time()
    os.makedirs(os.path.join(a.out, a.arm), exist_ok=True)
    od = os.path.join(a.out, a.arm)
    _log(f'{a.arm}: loading checkpoint and dataset (villa host inputs)')
    ckpt, ctx, transform, dr, zb, ze, cfg, paths = _load_context(a.ckpt, a.dataset)
    patches = ctx.verified_patches_list
    patch_ids = list(ctx.verified_patches.keys())
    atlas = ctx.patch_atlas
    _log(f'{a.arm}: {len(patches)} patches, dr={float(dr):.3f} vox/winding, z=[{zb},{ze}), '
         f'load {time.time() - t0:.0f}s')
    tols = [float(t) for t in a.tolerances.split(',')]
    base = dict(sm.metrics_config)
    evals = {}
    for t in tols:
        sm.metrics_config.clear()
        sm.metrics_config.update(base)
        sm.metrics_config['satisfaction_distance_tolerance'] = t
        t1 = time.time()
        ev = sm.evaluate_patch_satisfaction_packed(transform, dr, patches, atlas, zb, ze,
                                                   include_splicing=False)
        evals[t] = ev
        _log(f'{a.arm}: tolerance {t:g} vox evaluated in {time.time() - t1:.1f}s')
    sm.metrics_config.clear()
    sm.metrics_config.update(base)
    ev0 = evals[tols[0]]
    offsets = ev0.patch_offsets.numpy()
    for t, ev in evals.items():   # every pass must pack the same quads
        assert np.array_equal(ev.patch_offsets.numpy(), offsets)
    cen, nrm, qarea = _quad_geometry(atlas, ev0.corner_vertex_ids)
    _log(f'{a.arm}: quad geometry for {len(cen):,} quads')
    pairs_src = a.pairs_from or a.dataset
    pairs, psumm = load_relative_pairs(os.path.join(pairs_src, 'relative_windings.json'), a.voxel_um)
    pid_set = {str(p) for p in patch_ids}
    matched = sum(1 for k in pairs if k in pid_set)
    _log(f'{a.arm}: relative-pair patches matched to loaded patches: {matched}/{len(pairs)}')
    radii = [float(r) for r in a.radius.split(',')]
    regs = {r: _regimes(patch_ids, offsets, cen, pairs, r) for r in radii}
    _log(f'{a.arm}: regimes for radii {radii}')
    cm2 = (a.voxel_um * 1e-4) ** 2
    nominal_total = float(sum(float(p.area) for p in patches))
    res = dict(arm=a.arm, ckpt=os.path.abspath(a.ckpt), dataset=os.path.abspath(a.dataset),
               pairs_from=os.path.abspath(pairs_src), voxel_um=a.voxel_um,
               patches=len(patches), quads=int(len(cen)), dr_vox=float(dr), z=[zb, ze],
               ckpt_iteration=int(ckpt.get('completed_iterations', -1)),
               num_windings_cfg=int(cfg.get('model_gap_expander_num_windings', -1)),
               capacity_windings_cfg=int(cfg.get('model_gap_expander_capacity_windings', -1)),
               shell_outer_winding_idx_cfg=int(cfg.get('shell_outer_winding_idx', -1)),
               area3d_total_cm2=float(np.nansum(qarea) * cm2), pair_summary=psumm,
               pair_patches_matched=[matched, len(pairs)],
               villa_metrics_config=base, tolerances={})
    tw = ev0.target_winding_indices.cpu().numpy()
    ok_tw = tw >= 0
    res['snapped_winding_range'] = [int(tw[ok_tw].min()), int(tw[ok_tw].max())] if ok_tw.any() else None
    bits = np.zeros(len(cen), np.uint8)
    for k, (t, ev) in enumerate(evals.items()):
        prof = ev.profiles['strict']
        sat = prof.packed_satisfied_quads.numpy().astype(bool)
        bits |= (sat.astype(np.uint8) << k)
        ent = dict(placed_area3d_cm2=float(np.nansum(qarea[sat]) * cm2),
                   placed_area_nominal_cm2=float(prof.satisfied_areas.sum()) * cm2,
                   total_area_nominal_cm2=float(prof.total_areas.sum()) * cm2,
                   satisfied_patches=int(prof.satisfied_patches.sum()),
                   placed_quads=int(sat.sum()))
        ua, un = _unique_area_cm2(ev, sat, dr, a.voxel_um)
        ent['placed_unique_cm2'] = ua
        for r, reg in regs.items():
            ent[f'by_regime_r{int(r)}'] = {
                REGIMES[i]: dict(placed_cm2=float(np.nansum(qarea[sat & (reg == i)]) * cm2),
                                 total_cm2=float(np.nansum(qarea[reg == i]) * cm2)) for i in range(4)}
        res['tolerances'][f'{t:g}'] = ent
        _log(f'{a.arm}: tol {t:g}: placed {ent["placed_area3d_cm2"]:.2f} of {res["area3d_total_cm2"]:.2f} cm2 '
             f'(unique {ua:.2f})')
    ua_all, _ = _unique_area_cm2(ev0, np.ones(len(cen), bool), dr, a.voxel_um)
    res['unique_all_evaluated_cm2'] = ua_all
    res['nominal_total_all_patches_cm2'] = nominal_total * cm2
    np.savez_compressed(os.path.join(od, 'quads.npz'), bits=bits, tolerances=np.array(tols),
                        patch_offsets=offsets, target_winding=tw.astype(np.int32),
                        area3d=qarea, **{f'regime_r{int(r)}': g for r, g in regs.items()})
    # quad centres + normals for the picture's support map (RENDER reads them)
    np.save(os.path.join(od, 'quad_cn.npy'), np.concatenate([cen, nrm], 1))
    with open(os.path.join(od, 'patch_ids.txt'), 'w') as f:
        f.write('\n'.join(str(p) for p in patch_ids))
    t1 = time.time()
    pw = _pairs_w(transform, dr, pairs_src)
    np.savez_compressed(os.path.join(od, 'pairs.npz'),
                        **{f'{k.split(".")[0]}__{f}': v for k, d in pw.items() for f, v in d.items()})
    _log(f'{a.arm}: fitted w at {sum(len(d["w"]) for d in pw.values()):,} pairs in {time.time() - t1:.0f}s')
    res['wall_s'] = round(time.time() - t0, 1)
    try:
        res['cuda_max_allocated_gb'] = round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)
    except Exception:
        pass
    json.dump(res, open(os.path.join(od, 'place.json'), 'w'), indent=1)
    _log(f'{a.arm}: wrote {od}/place.json ({res["wall_s"]}s)')


def _fitted_delta(d, sign_seam):
    return np.round((d['w'][:, 1] - d['w'][:, 0]) + sign_seam * (d['adj'][:, 1] - d['adj'][:, 0])).astype(np.int64)


def _arbiter(pa, pb, voxel_um):
    """Arbiter tables from the two arms' pairs.npz. Conventions (seam sign s in {+1,-1}; index
    sign c in {+1,-1}: ours = c * (wind_b - wind_a)) are chosen once, on arm (a)'s pairs only,
    as those maximising agreement (arm a is fitted to them), and are recorded with both rates."""
    from .regime import regime_code
    out = {}
    rel_a = {k.split('__', 1)[1]: pa[k] for k in pa.files if k.startswith('relative_windings__')}
    rel_b = {k.split('__', 1)[1]: pb[k] for k in pb.files if k.startswith('relative_windings__')}
    same_a = {k.split('__', 1)[1]: pa[k] for k in pa.files if k.startswith('same_windings__')}
    same_b = {k.split('__', 1)[1]: pb[k] for k in pb.files if k.startswith('same_windings__')}
    conv = {}
    if same_a:
        z = {s: float((_fitted_delta(same_a, s) == 0).mean()) for s in (1, -1)}
        conv['seam_sign_same_zero_rate'] = z
    s = 1
    if rel_a:
        ours_raw = np.round(rel_a['wind'][:, 1] - rel_a['wind'][:, 0]).astype(np.int64)
        rates = {}
        for s_ in (1, -1):
            fa = _fitted_delta(rel_a, s_)
            for c in (1, -1):
                rates[(s_, c)] = float((fa == c * ours_raw).mean())
        s, c = max(rates, key=rates.get)
        conv['rel_rates_arm_a'] = {f'seam{k[0]:+d}_idx{k[1]:+d}': v for k, v in rates.items()}
        conv['chosen'] = dict(seam_sign=s, index_sign=c)
        ours = c * ours_raw
        fa, fb = _fitted_delta(rel_a, s), _fitted_delta(rel_b, s)
        reg = regime_code(rel_a['sep_vox'] * voxel_um)
        fin = np.isfinite(rel_a['w']).all(1) & np.isfinite(rel_b['w']).all(1)
        tab = {}
        for i, name in enumerate(REGIMES[:3]):
            m = fin & (reg == i)
            n = int(m.sum())
            disp = m & (fa != fb)
            nd = int(disp.sum())
            tab[name] = dict(
                pairs=n,
                a_equals_ours=float((fa[m] == ours[m]).mean()) if n else None,
                b_equals_ours=float((fb[m] == ours[m]).mean()) if n else None,
                a_fitted_zero=float((fa[m] == 0).mean()) if n else None,
                b_fitted_zero=float((fb[m] == 0).mean()) if n else None,
                disputed=nd, disputed_share=nd / n if n else None,
                among_disputed=dict(a_matches=float((fa[disp] == ours[disp]).mean()) if nd else None,
                                    b_matches=float((fb[disp] == ours[disp]).mean()) if nd else None,
                                    neither=float(((fa[disp] != ours[disp]) & (fb[disp] != ours[disp])).mean()) if nd else None))
        out['relative_by_regime'] = tab
        out['relative_unevaluated'] = int((~fin).sum())
    if same_a and same_b:
        fa, fb = _fitted_delta(same_a, s), _fitted_delta(same_b, s)
        fin = np.isfinite(same_a['w']).all(1) & np.isfinite(same_b['w']).all(1)
        reg = regime_code(same_a['sep_vox'] * voxel_um)
        out['same_windings'] = dict(
            pairs=int(fin.sum()), a_zero=float((fa[fin] == 0).mean()), b_zero=float((fb[fin] == 0).mean()),
            disputed_share=float((fa[fin] != fb[fin]).mean()),
            by_anchor_distance={REGIMES[i]: dict(pairs=int((fin & (reg == i)).sum()),
                                                  a_zero=float((fa[fin & (reg == i)] == 0).mean()) if (fin & (reg == i)).any() else None,
                                                  b_zero=float((fb[fin & (reg == i)] == 0).mean()) if (fin & (reg == i)).any() else None)
                                for i in range(3)})
    out['conventions'] = conv
    out['note'] = ('Fitted delta = round(w_B - w_A + s*(seam_B - seam_A)), w = shifted_radius/dr from villa '
                   'winding_at_points, seam from villa unwrap_shifted_radii. Conventions chosen on arm (a) only. '
                   'Agreement with our index is not correctness: no human adjudication, patches are machine traces.')
    return out


def _satisfied_fitted_check(tgz, place):
    """Compare villa's own end-of-fit satisfied area (6 vox) with our 6-vox pass."""
    if not tgz or not os.path.exists(tgz):
        return None
    with tarfile.open(tgz) as t:
        names = [m for m in t.getmembers() if m.name.endswith('satisfied_fitted.json')]
        if not names:
            return dict(found=False)
        d = json.load(t.extractfile(names[0]))
    items = d if isinstance(d, list) else d.get('patches', d.get('items', []))
    sat = sum(float(x.get('satisfied_area', 0)) for x in items if isinstance(x, dict))
    tot = sum(float(x.get('total_area', 0)) for x in items if isinstance(x, dict))
    six = place['tolerances'].get('6')
    cm2 = (place['voxel_um'] * 1e-4) ** 2
    return dict(found=True, member=names[0].name, villa_satisfied_cm2=sat * cm2, villa_total_cm2=tot * cm2,
                ours_6vox_nominal_cm2=six['placed_area_nominal_cm2'] if six else None,
                ours_6vox_total_nominal_cm2=six['total_area_nominal_cm2'] if six else None)


def cmd_combine(a):
    arms = {}
    for arm in a.arms:
        arms[arm] = json.load(open(os.path.join(a.out, arm, 'place.json')))
    summ = dict(arms=arms, gap={}, disagreement={}, cross_check={})
    rs = dict(kv.split('=', 1) for kv in (a.run_small or []))
    for arm, p in arms.items():
        summ['cross_check'][arm] = _satisfied_fitted_check(rs.get(arm), p)
    if len(a.arms) == 2:
        A, B = a.arms
        qa = np.load(os.path.join(a.out, A, 'quads.npz'))
        qb = np.load(os.path.join(a.out, B, 'quads.npz'))
        aligned = np.array_equal(qa['patch_offsets'], qb['patch_offsets'])
        summ['quads_aligned'] = bool(aligned)
        cm2 = (arms[A]['voxel_um'] * 1e-4) ** 2
        for tk in arms[A]['tolerances']:
            ga, gb = arms[A]['tolerances'][tk], arms[B]['tolerances'][tk]
            g = dict(all=ga['placed_area3d_cm2'] - gb['placed_area3d_cm2'])
            for rk in [k for k in ga if k.startswith('by_regime_')]:
                g[rk] = {r: ga[rk][r]['placed_cm2'] - gb[rk][r]['placed_cm2'] for r in REGIMES}
            summ['gap'][tk] = g
        if aligned:
            area = qa['area3d']
            for k, t in enumerate(qa['tolerances']):
                sa = (qa['bits'] >> k) & 1 == 1
                sb = (qb['bits'] >> k) & 1 == 1
                reg = qa['regime_r64'] if 'regime_r64' in qa.files else np.full(len(sa), 3)
                d = {}
                for i, r in enumerate(REGIMES):
                    m = reg == i
                    d[r] = dict(both_cm2=float(np.nansum(area[m & sa & sb]) * cm2),
                                a_only_cm2=float(np.nansum(area[m & sa & ~sb]) * cm2),
                                b_only_cm2=float(np.nansum(area[m & ~sa & sb]) * cm2),
                                neither_cm2=float(np.nansum(area[m & ~sa & ~sb]) * cm2))
                summ['disagreement'][f'{t:g}'] = dict(by_regime_r64=d)
        pa = np.load(os.path.join(a.out, A, 'pairs.npz'))
        pb = np.load(os.path.join(a.out, B, 'pairs.npz'))
        summ['arbiter'] = _arbiter(pa, pb, arms[A]['voxel_um'])
        if a.flags and aligned:
            summ['flag_split'] = _flag_table(a.out, A, B, a.flags, cm2)
    json.dump(summ, open(os.path.join(a.out, 'place_summary.json'), 'w'), indent=1)
    _write_table(summ, a.out, a.arms)
    _log(f'wrote {a.out}/place_summary.json and place_table.md')


def _flag_sets(path):
    """SessA checker unsatisfied.csv -> (all flagged patch ids, switch-verdict patch ids), as strings."""
    import csv
    allf, sw = set(), set()
    with open(path) as f:
        for r in csv.DictReader(f):
            for k in ('patch_a', 'patch_b'):
                allf.add(str(r[k]))
                if r.get('verdict', '') == 'switch':
                    sw.add(str(r[k]))
    return allf, sw


def _flag_table(out, A, B, flags_path, cm2):
    """Placed-within-tolerance area per arm by patch class (flagged / clean) x regime (r = 64 vox)."""
    qa = np.load(os.path.join(out, A, 'quads.npz'))
    qb = np.load(os.path.join(out, B, 'quads.npz'))
    if not np.array_equal(qa['patch_offsets'], qb['patch_offsets']):
        return dict(error='quad packing differs between arms')
    pids = open(os.path.join(out, A, 'patch_ids.txt')).read().split('\n')
    off = qa['patch_offsets']
    allf, sw = _flag_sets(flags_path)
    per_patch_all = np.array([p in allf for p in pids])
    per_patch_sw = np.array([p in sw for p in pids])
    counts = np.diff(off)
    area = qa['area3d']
    reg = qa['regime_r64']
    res = dict(flags_file=os.path.abspath(flags_path), patches=len(pids),
               flagged_patches=int(per_patch_all.sum()), switch_patches=int(per_patch_sw.sum()),
               flagged_ids_matched=len(allf & set(pids)), flagged_ids_in_file=len(allf))
    for vname, pp in (('all_unsatisfied', per_patch_all), ('switch_only', per_patch_sw)):
        cls = np.repeat(pp, counts)
        tab = {}
        for k, t in enumerate(qa['tolerances']):
            sa = ((qa['bits'] >> k) & 1) == 1
            sb = ((qb['bits'] >> k) & 1) == 1
            d = {}
            for cname, cm in (('flagged', cls), ('clean', ~cls)):
                for i, r in enumerate(REGIMES + ('all',)):
                    m = cm & (reg == i) if r != 'all' else cm
                    tot = float(np.nansum(area[m]) * cm2)
                    pa = float(np.nansum(area[m & sa]) * cm2)
                    pb = float(np.nansum(area[m & sb]) * cm2)
                    d[f'{cname}|{r}'] = dict(total_cm2=tot, a_cm2=pa, b_cm2=pb, gap_cm2=pa - pb)
            tab[f'{t:g}'] = d
        res[vname] = tab
    return res


def _write_table(summ, out, arm_names):
    L = ['# PLACE results', '']
    for tk in next(iter(summ['arms'].values()))['tolerances']:
        L += [f'## Placed area within {tk} voxel(s) (3-D quad area, cm²; sum over patches)', '',
              '| regime (r=64 vox) | ' + ' | '.join(f'{a} placed / total' for a in arm_names)
              + (' | gap a−b |' if len(arm_names) == 2 else ' |'),
              '|---|' + '---|' * (len(arm_names) + (1 if len(arm_names) == 2 else 0))]
        for r in REGIMES + ('all',):
            cells = []
            for a in arm_names:
                e = summ['arms'][a]['tolerances'][tk]
                if r == 'all':
                    cells.append(f'{e["placed_area3d_cm2"]:.2f} / {summ["arms"][a]["area3d_total_cm2"]:.2f}')
                else:
                    x = e['by_regime_r64'][r]
                    cells.append(f'{x["placed_cm2"]:.2f} / {x["total_cm2"]:.2f}')
            gap = ''
            if len(arm_names) == 2:
                g = summ['gap'][tk]
                gap = f' {g["all"] if r == "all" else g["by_regime_r64"][r]:+.2f} |'
            L.append(f'| {r} | ' + ' | '.join(cells) + ' |' + gap)
        L += ['', '| arm | unique placed cm² | villa nominal placed cm² | satisfied patches |', '|---|---|---|---|']
        for a in arm_names:
            e = summ['arms'][a]['tolerances'][tk]
            L.append(f'| {a} | {e["placed_unique_cm2"]:.2f} | {e["placed_area_nominal_cm2"]:.2f} | {e["satisfied_patches"]} |')
        L.append('')
    if 'arbiter' in summ and 'relative_by_regime' in summ['arbiter']:
        L += ['## Arbiter: relative-winding pairs, fitted Δ vs our index', '',
              '| regime | pairs | a = ours | b = ours | disputed | among disputed: a / b / neither |', '|---|---|---|---|---|---|']
        for r, x in summ['arbiter']['relative_by_regime'].items():
            f = lambda v: 'n/a' if v is None else f'{v:.3f}'
            ad = x['among_disputed']
            L.append(f'| {r} | {x["pairs"]} | {f(x["a_equals_ours"])} | {f(x["b_equals_ours"])} | '
                     f'{x["disputed"]} ({f(x["disputed_share"])}) | {f(ad["a_matches"])} / {f(ad["b_matches"])} / {f(ad["neither"])} |')
        L += ['', f'Conventions: `{json.dumps(summ["arbiter"]["conventions"].get("chosen"))}`', '']
    fs = summ.get('flag_split')
    if fs and 'all_unsatisfied' in fs:
        L += ['## Placed within 1 voxel by patch class (checker flags) and regime (cm²)', '',
              f"flagged = patch in any unsatisfied.csv row: {fs['flagged_patches']} of {fs['patches']} patches "
              f"(switch-verdict only: {fs['switch_patches']})", '']
        for vname in ('all_unsatisfied', 'switch_only'):
            d = fs[vname]['1']
            L += [f'### {vname}', '', '| class | regime | total | arm a | arm b | gap a−b |', '|---|---|---|---|---|---|']
            for c in ('flagged', 'clean'):
                for r in REGIMES + ('all',):
                    x = d[f'{c}|{r}']
                    L.append(f"| {c} | {r} | {x['total_cm2']:.2f} | {x['a_cm2']:.2f} | {x['b_cm2']:.2f} | {x['gap_cm2']:+.2f} |")
            L.append('')
        arb = summ.get('arbiter', {}).get('relative_by_regime', {})
        if arb:
            L.append('Arbiter beside it (relative pairs, fitted Δ = our index, a / b): ' + ', '.join(
                f"{r} {x['a_equals_ours']:.2f} / {x['b_equals_ours']:.2f}" for r, x in arb.items() if x.get('pairs')))
            L.append('')
    open(os.path.join(out, 'place_table.md'), 'w').write('\n'.join(L) + '\n')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    q = sp.add_parser('arm')
    q.add_argument('--arm', required=True)
    q.add_argument('--ckpt', required=True)
    q.add_argument('--dataset', required=True)
    q.add_argument('--pairs-from', default='')
    q.add_argument('--out', required=True)
    q.add_argument('--tolerances', default='1,2,6')
    q.add_argument('--radius', default='64,256')
    q.add_argument('--voxel-um', type=float, default=7.91)
    q = sp.add_parser('combine')
    q.add_argument('--out', required=True)
    q.add_argument('--arms', nargs='+', required=True)
    q.add_argument('--run-small', nargs='*', default=[])
    q.add_argument('--flags', default='', help="checker unsatisfied.csv (patch_a, patch_b, verdict): flagged/clean split")
    a = p.parse_args(argv)
    {'arm': cmd_arm, 'combine': cmd_combine}[a.cmd](a)


if __name__ == '__main__':
    main()
