"""SessA-6: the solve reproduces Q3c's committed slab-2 wrap index exactly at 134 um; the spacing port matches SessC."""
import filecmp
import json
from pathlib import Path

import numpy as np

from vc_sheet_check import solve as SV, spacing as SPC

REPO = Path(__file__).resolve().parents[4]


def test_slab2_exact_reproduction(tmp_path):
    _need = [REPO / "phase/x6/x6b_points.npz", REPO / "phase/x3/results/slab2/pairs.csv"]
    if not all(p.exists() for p in _need):   # release tree (release script, coordinator 16:31)
        import pytest
        pytest.skip("needs private-only slab-2 inputs (phase/x6/x6b_points.npz, phase/x3/results/slab2/pairs.csv)")
    E, nodes, xyz, axis_xy = SV.edges_from_slab2(REPO)
    st = SV.build_state(E, nodes, xyz, axis_xy, SV.SP_UM_Q3C)
    res = SV.solve(st, tiebreak=False)                     # committed Q3c path (pre-V1-15)
    SV.write_wrap_index(tmp_path / "wrap_index.csv", st, res)
    assert filecmp.cmp(tmp_path / "wrap_index.csv", REPO / "phase/p1page/p1b_q3c_k.csv", shallow=False)
    ref = json.load(open(REPO / "phase/p1page/p1b_q3c_k.json"))
    for k in ("s_chosen", "objectives", "objective", "n", "n_components"):
        assert res[k] == ref[k], k


def test_spacing_is_a_parameter():
    E = [dict(a=1, b=2, d_i=None, sep_ii_um=150.0, msep_um=90.0)]
    xyz = {1: np.array([10.0, 0, 0]), 2: np.array([11.0, 0, 0])}
    ax = lambda z: (np.zeros_like(z), np.zeros_like(z))
    s134 = SV.build_state(E, [1, 2], xyz, ax, 134.0)["E"][0]
    s162 = SV.build_state(E, [1, 2], xyz, ax, 162.0)["E"][0]
    assert (s134["d_ii"], s134["stevens"]) == (1, True)       # 150/134 -> 1; 90 > 79.06
    assert (s162["d_ii"], s162["stevens"]) == (1, False)      # 150/162 -> 1; 90 < 95.58


def test_box_spacing_synthetic_bands():
    """A 256^3 box of flat bands every 20 voxels (7 thick) measures 20.0 voxels, the SessC definition's own units."""
    z = np.arange(256)
    prof = ((z % 20) < 7).astype(np.float32) * 1000 + 100
    box = np.broadcast_to(prof[:, None, None], (256, 256, 256)).copy()
    r = SPC.box_spacings(box, np.array([128, 128, 128]))
    assert abs(r["spacing_median_vox"] - 20.0) < 1e-9


def test_flat_region_needs_patches(tmp_path):
    from vc_sheet_check import cli
    rc = cli.main_a42(["--region", "0", "0", "0", "128", "128", "128", "--volume", "x", "--out", str(tmp_path)])
    assert rc == 2 and json.load(open(tmp_path / "report.json"))["status"] == "error"


def test_input_hash_of_directory(tmp_path):
    from vc_sheet_check.region import _sha
    (tmp_path / "patch_1").mkdir(); (tmp_path / "patch_1" / "x.tif").write_bytes(b"abc")
    h1 = _sha(tmp_path); (tmp_path / "patch_1" / "x.tif").write_bytes(b"abd")
    assert h1.startswith("tree:") and _sha(tmp_path) != h1


def test_axis_rule_refuses_centroid_axis():
    """SessA-7: region mode never derives the axis from the region's own patch centroids, and uses the §2 axis only
    inside slab 2's X6 node extent."""
    import argparse
    import sys
    sys.path.insert(0, str(REPO / "phase/h1"))
    import pytest
    from vc_sheet_check import region as RG
    from vc_sheet_check.segment import InputError
    rows = [dict(cx=100.0 + i, cy=200.0, cz=3000.0, n=100) for i in range(5)]
    with pytest.raises(InputError):
        RG._axis(REPO, argparse.Namespace(axis="table", axis_file=None, origin=[4096, 2304, 768], shape=[384] * 3), rows)
    s4 = "https://dl.ash2txt.org/full-scrolls/Scroll4/PHerc1667.volpkg/volumes_zarr/20231117161658.zarr"
    other = "other-scan.volpkg/volumes_zarr/20000101000000.zarr"   # another scan, by path (no host)
    with pytest.raises(InputError):                            # outside slab 2 (z 2432)
        RG._axis(REPO, argparse.Namespace(axis="x6", axis_file=None, ct=s4, origin=[2432, 1536, 3968], shape=[384] * 3), rows)
    with pytest.raises(InputError):                            # a slab-2 box on another scan (SessA-8)
        RG._axis(REPO, argparse.Namespace(axis="x6", axis_file=None, ct=other, origin=[4096, 2304, 768], shape=[384] * 3), rows)
    for ct in (s4, str(REPO / "phase/data_small/fixture/ct.zarr")):   # URL, and a local crop named in .zattrs
        a = argparse.Namespace(axis="x6", axis_file=None, ct=ct, origin=[4096, 2304, 768], shape=[384] * 3)
        RG._axis(REPO, a, rows)
        assert a.axis_check["region_inside"] and a.axis_check["scan_id"] == "20231117161658"


def test_default_risk_model_is_z_free():
    import joblib
    m = joblib.load(REPO / "phase/tools/risk_model/risk_model_v2_noz.joblib")
    assert "z_um" not in m["active_features"] and m["version"] == "v2_noz"
