"""SessA tests: vc_sheet_check and pipeline9_filter against the fixture and committed slab-2 data (no network).

    python3 -m pytest phase/tools/vc_sheet_check/tests -q
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

R = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(R / "phase/tools/vc_sheet_check"), str(R / "phase/tools/pipeline9_filter"), str(R / "phase/tools")]

from vc_sheet_check import meshio, region, p9filter, cli  # noqa: E402
from pipeline9_filter import core as P9, cli as P9cli  # noqa: E402


# ------------------------------------------------------------------------------------------------ units

def test_obj_reader_edges_and_fan(tmp_path):
    p = tmp_path / "q.obj"
    p.write_text("v 1 2 3\nv 2 2 3\nv 2 3 3\nv 1 3 3\nvn 0 0 1\nf 1/1/1 2/2/2 3/3/3 4/4/4\n")
    m = meshio.read_mesh(p)
    assert m.kind == "obj" and m.faces.tolist() == [[0, 1, 2], [0, 2, 3]]
    assert sorted(map(tuple, m.edges.tolist())) == [(0, 1), (0, 2), (0, 3), (1, 2), (2, 3)]


def test_tifxyz_roundtrip_sets_removed_cells_to_minus_one(tmp_path):
    import tifffile
    g = np.stack(np.meshgrid(np.arange(4.0) + 10, np.arange(3.0) + 20, indexing="xy"), -1)
    for i, c in enumerate("xyz"):
        tifffile.imwrite(tmp_path / f"{c}.tif", (g[..., 0] if c == "x" else g[..., 1] if c == "y" else np.full(g.shape[:2], 5.0)).astype(np.float32))
    (tmp_path / "meta.json").write_text(json.dumps({"format": "tifxyz", "scale": [0.25, 0.25]}))
    m = meshio.read_mesh(tmp_path)
    assert m.shape == (3, 4) and m.valid.all() and len(m.edges) == 3 * 3 + 2 * 4
    keep = np.ones(12, bool); keep[5] = False
    meshio.write_tifxyz(tmp_path / "out", m, keep, {"removed_cells": 1})
    x = tifffile.imread(tmp_path / "out/x.tif")
    assert x[1, 1] == -1 and x[0, 0] == 10 and json.loads((tmp_path / "out/meta.json").read_text())["removed_cells"] == 1


def test_rf_rule_matches_p1b_synthetic():
    # p1b_rf_joins.py synthetic: a at 6.2 (k=5), b at 0.1 (k=6), s=+1 -> same sheet across the cut
    K = {1: (5, 6.2), 2: (6, 0.1), 3: (5, 1.0), 4: (5, 1.2), 5: (6, 1.2)}
    kept = region.rf_joins([(1, 2), (3, 4), (3, 5), (1, 9)], K, 1, {})
    assert kept == [(1, 2), (3, 4), (1, 9)]
    assert region.rf_joins([(3, 4)], K, 1, {(3, 4): 1}) == []          # direct measurement vetoes


def test_rel_filter_is_byte_identical(tmp_path):
    rel = tmp_path / "rel.csv"
    rows = [b"72,48,6.7e-05,0.0,0.188374\n", b"90,48,0.00015,1e-06,0.563963\r\n", b"150,48,0.00021,0.000279,0.227225\n"]
    rel.write_bytes(b"".join(rows))
    info = p9filter.filter_rel(rel, tmp_path / "o", [dict(patch_a=48, patch_b=90, risk=0.9, flagged=1, sep_um=12.0)], 0.33, {"contract": "v1"})
    assert (tmp_path / "o/rel_filtered.csv").read_bytes() == rows[0] + rows[2]
    assert info["rel_rows_removed"] == 1
    rem = list(csv.DictReader(open(tmp_path / "o/removed_joins.csv")))
    assert rem[0]["patch_a"] == "48" and rem[0]["contact"] == "1"


# ------------------------------------------------------------------------------------------------ fixture

@pytest.fixture(scope="module")
def fixture_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("fixA")
    assert cli.main(["fixture", "--out", str(out)]) == 0
    return out


def test_fixture_outputs_pass_contract_validator(fixture_out):
    r = subprocess.run([sys.executable, str(R / "phase/tools/test_fixture.py"), "--outputs", str(fixture_out)],
                       capture_output=True, text=True, cwd=R)
    assert r.returncode == 0 and "ALL PASS" in r.stdout, r.stdout[-2000:]


def test_fixture_counts_equal_golden_derived_values(fixture_out):
    rep = json.load(open(fixture_out / "report.json"))
    c = rep["counts"]
    # region A: 231 patches; golden flags among region-A pairs; pages at 0.1 cm2; §5.4 wrong-turn points
    assert (c["patches"], c["pairs_scored"], c["pairs_flagged"], c["pairs_flagged_contact"], c["pages"]) == (231, 507, 92, 11, 18)
    assert (c["wrong_turn_patches"], c["wrong_turn_points"]) == (86, 13125)
    m = rep["metrics"]["iii_rf_minus_flagged"]
    assert abs(m["m2_point"]["M2_point"] - 0.9792982705183713) < 1e-12
    assert abs(m["x6"]["M1"] - 0.744316680680899) < 1e-12
    key = lambda r: region.jkey(r["patch_a"], r["patch_b"])       # golden keeps X8's pair order; compare unordered
    gs = {key(r): int(r["flagged"]) for r in csv.DictReader(open(R / "phase/data_small/fixture/golden/switch_risk.csv"))}
    mine = {key(r): int(r["flagged"]) for r in csv.DictReader(open(fixture_out / "switch_risk.csv"))}
    assert len(mine) == 507 and all(mine[k] == gs[k] for k in mine)
    # clusters link pairs (and patches) as units: every flagged pair and wrong-turn patch appears exactly once
    cl = rep["clusters"]
    assert sum(x["n_pairs"] for x in cl if x["kind"] == "suspect_join") == c["pairs_flagged"]
    assert sum(x["n_patches"] for x in cl if x["kind"] == "wrong_turn") == c["wrong_turn_patches"]


def test_fixture_hybrid_intermediate_pages_equal_golden():
    import metrics as M
    F = R / "phase/data_small/fixture"
    G = json.load(open(F / "golden/pages_metrics.json")); gmin = G["iii_rf"]["page_min_mm2"]
    area = M.bbox_area_mm2(F / "patches.csv"); allp = sorted(int(r["id"]) for r in csv.DictReader(open(F / "patches.csv")))
    U = sorted(set(P9.read_rel_pairs(F / "rel.csv")) - set(P9.read_rel_pairs(R / "phase/x10/flip1_pairs.csv")))
    K, s = P9.read_wrap(R / "phase/p1page/p1b_q3c_k.csv"); bad = P9.read_ids(F / "pipeline9_badpatches_b.csv")
    rf, _ = P9.rf_joins(U, K, s, P9.read_direct(R / "phase/x10/x7_v7_edges.csv"))
    assert [list(x) for x in M.pages(rf, allp, area, gmin)] == G["iii_rf"]["pages"]
    ii = [k for k in U if k[0] not in bad and k[1] not in bad]
    assert [list(x) for x in M.pages(ii, allp, area, gmin)] == G["ii_pipeline9_deletions"]["pages"]


# ------------------------------------------------------------------------------------------------ slab 2

def test_slab2_hybrid_row_reproduces_p1e(tmp_path):
    assert P9cli.main(["slab2", "--out", str(tmp_path), "--bootstrap"]) == 0
    r = json.load(open(tmp_path / "filter.json"))
    assert (r["n_joins_universe"], r["n_rf"], r["n_joins"], r["pages"], r["pruned_patches"]) == (10240, 9825, 8007, 23, 0)
    m = r["metrics"]["per_patch_layer"]; ci = r["metrics"]["per_patch_layer_ci95"]
    g = json.load(open(R / "phase/p1page/p1e_frontier.json"))["combined"]
    for k_mine, k_g in (("page_area_cm2", "page_area_cm2"), ("M1", "M1"), ("M2_patch", "M2"), ("M3_per_cm2", "M3_per_cm2")):
        assert round(m[k_mine], 4) == g["point"][k_g]
        assert ci[k_mine] == g["ci95"][k_g]
    src = set(open(R / "phase/x5/rel.csv", "rb").read().splitlines(keepends=True))
    out = open(tmp_path / "rel.csv", "rb").read().splitlines(keepends=True)
    assert len(out) == 8007 and all(line in src for line in out)


# ------------------------------------------------------------------------------------------------ SessA-4

def test_overlay_writer_equals_contract_io(tmp_path):
    import zarr
    import contract_io as CIO
    from vc_sheet_check import zarrio
    rng = np.random.default_rng(0); arr = np.zeros((200, 150, 260), np.uint8)
    arr[rng.integers(0, 200, 300), rng.integers(0, 150, 300), rng.integers(0, 260, 300)] = rng.integers(1, 3, 300)
    org = [4224, 2560, 640]
    CIO.write_overlay_fullframe(tmp_path / "ref.zarr", arr, org, CIO.PHERC1667_SCAN_SHAPE0)  # item-159: shape now explicit
    zarrio.write_overlay_fullframe_sparse(tmp_path / "mine.zarr", zarrio.region_to_blocks(arr, org), CIO.SCAN_LEVEL_SHAPES[0], org, arr.shape)
    for lv in range(6):
        a = zarr.open_array(str(tmp_path / f"ref.zarr/{lv}"), mode="r"); b = zarr.open_array(str(tmp_path / f"mine.zarr/{lv}"), mode="r")
        s = 2 ** lv; lo = [o // s for o in org]; hi = [-(-(o + n) // s) for o, n in zip(org, arr.shape)]
        assert np.array_equal(a[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]], b[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]])
        ka = sorted(p.relative_to(tmp_path / "ref.zarr").as_posix() for p in (tmp_path / f"ref.zarr/{lv}").rglob("*") if p.is_file() and not p.name.startswith("."))
        kb = sorted(p.relative_to(tmp_path / "mine.zarr").as_posix() for p in (tmp_path / f"mine.zarr/{lv}").rglob("*") if p.is_file() and not p.name.startswith("."))
        assert ka == kb
        assert json.load(open(tmp_path / f"ref.zarr/{lv}/.zarray")) == json.load(open(tmp_path / f"mine.zarr/{lv}/.zarray"))


def test_segment_without_axis_file_exits_2(tmp_path):
    import tifffile
    for c in "xyz":
        tifffile.imwrite(tmp_path / f"{c}.tif", np.full((3, 3), 100.0, np.float32))
    rc = cli.main_a42(["--segment", str(tmp_path), "--volume", "unused", "--out", str(tmp_path / "o")])
    assert rc == 2
    rep = json.load(open(tmp_path / "o/report.json"))
    assert rep["status"] == "error" and "axis file" in rep["error"] and not (tmp_path / "o/overlay.zarr").exists()


def test_dense_pairs_are_the_100_400um_neighbourhoods():
    from vc_sheet_check import check as CK
    H, W = 6, 7; step = 20.0          # 20 L0 voxels = 158.2 um, like the Scroll 4 autogen
    g = np.stack(np.meshgrid(np.arange(W) * step + 100, np.arange(H) * step + 100, indexing="xy"), -1)
    xyz = np.concatenate([g, np.full((H, W, 1), 500.0)], -1).reshape(-1, 3)
    valid = np.ones(H * W, bool)
    m = meshio.Mesh(xyz=xyz, valid=valid, edges=meshio._grid_edges(H, W, valid), kind="tifxyz", source="", grid=np.arange(H * W).reshape(H, W))
    ia, ib, d = CK.dense_pairs(m, 7.91)
    # path along grid edges within [100, 400] um: 1 step (158) and 2 steps (316, straight or L-shaped), not 3 (475)
    got = {(int(a), int(b)) for a, b in zip(ia, ib)}
    exp = set()
    for i in range(H * W):
        r, c = divmod(i, W)
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if 1 <= abs(dr) + abs(dc) <= 2 and 0 <= r + dr < H and 0 <= c + dc < W:
                    j = (r + dr) * W + c + dc
                    if j > i:
                        exp.add((i, j))
    assert got == exp and np.all((d >= 100) & (d <= 400))


def test_sampled_mode_has_no_floor():
    from vc_sheet_check import check as CK
    H, W = 3, 3; xyz = np.stack(np.meshgrid(np.arange(W) * 20.0 + 100, np.arange(H) * 20.0 + 100, indexing="xy"), -1)
    xyz = np.concatenate([xyz, np.full((H, W, 1), 500.0)], -1).reshape(-1, 3); valid = np.ones(9, bool)
    m = meshio.Mesh(xyz=xyz, valid=valid, edges=meshio._grid_edges(H, W, valid), kind="tifxyz", source="", grid=np.arange(9).reshape(H, W))
    class StubField:                                      # snaps every point to itself; every path in support, count 0
        def snap(self, p, tmax):
            return np.asarray(p, float), np.zeros(len(p))
        def count(self, a, b):
            return np.zeros(len(a)), np.ones(len(a), bool)
    res = CK.run_check(m, StubField(), 10.0, 7.91, "tiny")      # area x 400/cm2 is a handful (the old floor drew 500)
    assert res["n_pairs_target"] == round(CK.area_cm2(m, 7.91) * CK.PAIRS_PER_CM2) < 10


def test_axis_file_formats_a12_1(tmp_path):
    """open item 50 / A12.1: our z,y,x CSV, villa's umbilicus.json and the headerless text read identically; outside queries counted."""
    import json as _json
    from pathlib import Path as _P
    import numpy as _np
    from vc_sheet_check import field as _F
    src = _P(__file__).resolve().parents[2] / "axis/pherc1667_x3slab2_axis.csv"
    a = _F.load_axis_file(src)
    j = tmp_path / "umbilicus.json"
    j.write_text(_json.dumps({"control_points": [dict(z=float(z), y=float(y), x=float(x)) for z, y, x in zip(a.z, a.y, a.x)]}))
    t = tmp_path / "axis_zyx.txt"; _np.savetxt(t, _np.stack([a.z, a.y, a.x], 1), delimiter=", ", fmt="%.6f")
    b, c = _F.load_axis_file(j), _F.load_axis_file(t)
    zq = _np.linspace(a.z[0] - 50, a.z[-1] + 50, 97)
    xa, ya = a(zq)
    for o in (b, c):
        xo, yo = o(zq)
        assert _np.abs(xa - xo).max() < 1e-5 and _np.abs(ya - yo).max() < 1e-5
    assert a.outside == b.outside == c.outside > 0 and a.format.startswith("csv") and b.format.startswith("umbilicus")
    bad = tmp_path / "scaled.json"; bad.write_text(_json.dumps({"coordinate_scale": 2.0, "control_points": [dict(z=0, y=0, x=0), dict(z=1, y=0, x=0)]}))
    try:
        _F.load_axis_file(bad); assert False, "coordinate_scale 2 must be refused"
    except ValueError:
        pass
