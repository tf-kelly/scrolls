"""Vendored, unmodified copies of frozen phase/ modules. See PROVENANCE.json.

s1b_mesh_check imports its siblings by bare name ("common" = phase/x2/common.py,
"core" = phase/x3/switchwitness/core.py) after editing sys.path to the repo.
Instead of editing the frozen file, mesh_check() registers those two names in
sys.modules only for the duration of the import and then restores them.
"""
import importlib
import sys

_MC = None


def mesh_check():
    global _MC
    if _MC is None:
        from . import x2_common, switchwitness_core
        saved = {k: sys.modules.get(k) for k in ("common", "core")}
        sys.modules["common"], sys.modules["core"] = x2_common, switchwitness_core
        try:
            _MC = importlib.import_module(__name__ + ".s1b_mesh_check")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
    return _MC
