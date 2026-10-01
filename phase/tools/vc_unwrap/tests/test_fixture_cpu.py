"""CPU test of vc-unwrap on fixture region A: check + export, and the fit's refusal without a GPU (about 3 min).
Needs villa's spiral-fitting at f4570bf in $VILLA and a python with villa's loader dependencies in $VILLA_PYTHON
(default: this interpreter). Run: VILLA=/path/villa/spiral-fitting python3 -m pytest phase/tools/vc_unwrap/tests -q"""
import json, os, subprocess, sys
from pathlib import Path

import pytest

VILLA = os.environ.get("VILLA")


@pytest.mark.skipif(not VILLA, reason="set VILLA to villa/spiral-fitting at f4570bf")
def test_check_export_and_fit_refusal(tmp_path):
    from vc_unwrap.cli import main
    py = os.environ.get("VILLA_PYTHON", sys.executable)
    assert main(["run", "--fixture", "--until", "export", "--villa", VILLA, "--python", py, "--out", str(tmp_path)]) == 0
    m = json.load(open(tmp_path / "UNWRAP_MANIFEST.json")); e = json.load(open(tmp_path / "EXPORT_MANIFEST.json"))
    assert m["status"] == "ok" and m["stages"]["check"]["result"]["wrap_index"]["s_chosen"] == 1
    assert (tmp_path / "check/overlay.zarr").is_dir() and (tmp_path / "check/unsatisfied.csv").exists()
    assert e["name_check"]["passed"] and e["point_pairs"] > 0
    assert all((tmp_path / "dataset" / f).exists() for f in ("same_windings.json", "relative_windings.json", "umbilicus.json", "spiral-scroll.json"))
    import torch
    if not torch.cuda.is_available():
        assert main(["fit", "--villa", VILLA, "--python", py, "--steps", "200", "--out", str(tmp_path)]) == 2
