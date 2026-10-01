"""Run villa's headless fit_spiral.py unchanged, and on exit record wall time and peak memory (SessB).
Usage (cwd = villa/spiral-fitting): python run_fit.py MEM_JSON -- --dataset ROOT
Writes MEM_JSON: wall_s, torch.cuda max_memory_allocated / max_memory_reserved (GB), peak host RSS (GB), exit status.
"""
import atexit, json, os, resource, runpy, sys, time

sys.path.insert(0, os.getcwd())   # villa/spiral-fitting: its modules import each other as top-level names

out, argv = sys.argv[1], sys.argv[sys.argv.index("--") + 1:]
t0 = time.time(); status = {"exit": None}


def record():
    rec = dict(wall_s=round(time.time() - t0, 1), exit=status["exit"],
               host_peak_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20, 3))
    try:
        import torch
        if torch.cuda.is_available():
            rec.update(gpu=torch.cuda.get_device_name(0), capability=list(torch.cuda.get_device_capability(0)),
                       cuda_max_allocated_gb=round(torch.cuda.max_memory_allocated() / 2**30, 3),
                       cuda_max_reserved_gb=round(torch.cuda.max_memory_reserved() / 2**30, 3),
                       torch=torch.__version__, torch_cuda=torch.version.cuda)
    except Exception as e:  # never mask the fit's own result
        rec["torch_error"] = repr(e)
    json.dump(rec, open(out, "w"), indent=1)


atexit.register(record)
sys.argv = ["fit_spiral.py"] + argv
try:
    runpy.run_path("fit_spiral.py", run_name="__main__")
    status["exit"] = 0
except SystemExit as e:
    status["exit"] = e.code if isinstance(e.code, int) else 1
    raise
except BaseException as e:
    status["exit"] = f"{type(e).__name__}: {e}"[:300]
    raise
