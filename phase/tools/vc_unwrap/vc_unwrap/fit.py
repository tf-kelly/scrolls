"""Stage 3, fit: villa's headless fit_spiral.py (villa f4570bf), unchanged, on the exported dataset root. Needs an NVIDIA
GPU: villa's fit selects CUDA unconditionally and uses Triton kernels. The settings are SessB's arm (a) (`point` config,
phase/vm_spiral/cfg/point.json): our relative and same-winding point collections are the only inputs besides the
patches; tracks, fibres, normals, absolute points and the outer shell are off. The z range is the checked region's.
Every `--sync-every` seconds, and when the fit ends, `--sync` (a shell command, e.g. `gsutil -m rsync -r OUT gs://...`)
is run, so outputs leave the machine as they are produced (project owner, 2026-09-28: a job that uploads only at exit fails)."""
import json
import re, os, subprocess, sys, time
from pathlib import Path

POINT_CONFIG = {"input_use_tracks": False, "input_use_fibers": False, "input_use_fiber_directions": False,
                "input_use_pcl_absolute": False, "input_use_pcl_drawn_control_points": False, "input_use_normals": False,
                "input_use_gradient_magnitude": False, "input_use_winding_inference": False, "input_use_outer_shell": False,
                "input_use_pcl_relative": True, "input_use_pcl_same_winding": True}


def sync(cmd, log):
    if cmd:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        log.write(f"[sync {time.strftime('%H:%M:%SZ', time.gmtime())}] exit {r.returncode}\n"); log.flush()


EXCEED = re.compile(r"WARNING: .* exceeding (gap_expander_capacity_windings|flow_bounds_radius)")  # villa f4570bf spiral_helpers.py:1232


def run_fit(out, villa, zrange, steps, sync_cmd=None, sync_every=300, python=sys.executable, allow_no_gpu=False, num_windings=None,
            num_windings_source=None, capacity_windings=None, capacity_source=None):
    villa, fit = Path(villa), out / "fit"; fit.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run([python, "-c", "import torch; print(int(torch.cuda.is_available()))"], capture_output=True, text=True)
    if probe.stdout.strip() != "1" and not allow_no_gpu:
        raise SystemExit("fit: no CUDA device. villa's Spiral fit needs an NVIDIA GPU (see README: GPU required)")
    cfg = dict(POINT_CONFIG, z_begin=int(zrange[0]), z_end=int(zrange[1]), optimizer_num_training_steps=int(steps))
    if num_windings is None:                         # villa f4570bf's config.py defaults both to 130 (Scroll 1's count)
        raise SystemExit("fit: the scroll's winding count must be set explicitly (--num-windings); villa's default is Scroll 1's 130")
    # villa f4570bf (spiral_helpers.py:1160) requires capacity >= shell_outer_winding_idx + 3; its defaults are 130 / 144,
    # 14 of headroom. Keep that headroom (item-163: the ARC arms failed at model construction with 160 / 160 / 144).
    cap = int(capacity_windings) if capacity_windings is not None else max(144, int(num_windings) + 14)
    if cap < int(num_windings) + 3:                  # villa refuses this at model construction; say so before the GPU starts
        raise SystemExit(f"fit: capacity {cap} < windings {num_windings} + 3 (villa f4570bf spiral_helpers.py:1160)")
    cfg.update(model_gap_expander_num_windings=int(num_windings), shell_outer_winding_idx=int(num_windings),
               model_gap_expander_capacity_windings=cap)
    (fit / "config_overrides.json").write_text(json.dumps(cfg, indent=1) + "\n")
    env = dict(os.environ, FIT_SPIRAL_CONFIG_OVERRIDES=json.dumps(cfg), FIT_SPIRAL_RUN_DIR=str(fit / "run"),
               FIT_SPIRAL_METRICS_HISTORY=str(fit / "metrics.jsonl"), WANDB_MODE="disabled",
               FIT_SPIRAL_CACHE_DIR=str(fit / "cache/villa"), TRITON_CACHE_DIR=str(fit / "cache/triton"))
    t0 = time.time()
    with open(fit / "fit.log", "w") as log:
        p = subprocess.Popen([python, "-u", "fit_spiral.py", "--dataset", str(out / "dataset")], cwd=villa, env=env, stdout=log, stderr=subprocess.STDOUT)
        last = time.time(); gate = None
        while p.poll() is None:
            time.sleep(10)
            hits = [l for l in (fit / "fit.log").read_text(errors="replace").splitlines() if EXCEED.search(l)]
            if hits:                                 # item-164: villa only warns; this gate fails the fit instead
                gate = hits; p.terminate()
                try:
                    p.wait(60)
                except subprocess.TimeoutExpired:
                    p.kill()
                break
            if time.time() - last >= sync_every:
                sync(sync_cmd, log); last = time.time()
        rc = p.wait(); sync(sync_cmd, log)
    rec = dict(exit=rc, wall_s=round(time.time() - t0, 1), steps=int(steps), z_range=list(zrange), villa=str(villa),
               num_windings=dict(value=int(num_windings), source=num_windings_source,
                                 sets=["model_gap_expander_num_windings", "shell_outer_winding_idx"],
                                 capacity_windings=dict(value=cap, source=capacity_source or "max(144, num_windings + 14): villa's default headroom")),
               exceed_gate=dict(pattern=EXCEED.pattern, tripped=bool(gate), lines=(gate or [])[:20]),
               checkpoint=str(fit / "run/checkpoint_fitted.ckpt") if (fit / "run/checkpoint_fitted.ckpt").exists() else None)
    (fit / "FIT_RECORD.json").write_text(json.dumps(rec, indent=1) + "\n")
    if gate:
        raise SystemExit("fit: villa reports inputs beyond the fit's bounds; stopped before training (item-164):\n" + "\n".join(gate[:10]))
    if rc:
        raise SystemExit(f"fit: fit_spiral.py exited {rc} (see {fit / 'fit.log'})")
    return rec
