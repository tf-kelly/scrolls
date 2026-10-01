# SessB-3: whole-scroll villa Spiral fit on Oxford ARC (HTC)

**Aim.** Fit villa's Spiral model to the whole of PHerc1667 (all 56,968 patches) on one H100, in two arms, with the
same configuration SessB used on the slab:
- **(a)** our whole-scroll winding constraints;
- **(b)** no winding constraints.

Everything lives in `$DATA/vc_arc` (`<arc-project-dir>/<user>/vc_arc`). Checkpoints go to `$DATA` every
2,000 steps. If a job hits the 12-hour limit, resubmit it and it continues.

**Blocked until SessA-12 lands.** Arms (a) and (b) need SessA-12's whole-scroll files, listed as `PENDING` in
`bundle/INPUTS.sha256`:
- `umbilicus.json` (both arms);
- `same_windings.json` and `relative_windings.json` (arm a).

`test_job.sh` does not need them.

## Two routes, chosen by `setup.sh` and recorded in `$DATA/vc_arc/route.txt`
- **apptainer**: used if `apptainer`/`singularity` is on the PATH or loads as a module, and you supply the image
  (`SIF_URL`). The image `villa.sif` (3.6 GB) has torch 2.11.0 **built for CUDA 13.0** and needs NVIDIA driver ≥ 580.
  It could not be built with villa's exact CUDA 12.8 torch here, because this sandbox cannot reach `download.pytorch.org`.
- **venv**: used otherwise, or if the image will not run. `setup.sh` installs uv and Python 3.14 under `$DATA/vc_arc`
  and runs villa's own `uv sync --frozen` into `$DATA/vc_arc/env`. That is the **exact locked environment** (torch
  2.11.0+cu128), the same one SessB's L4 fits used. It needs internet on the login node (you confirmed it has) and a
  g++ ≥ 11 (`setup.sh` loads a GCC ≥ 11 module if the system compiler is older). Nothing is downloaded at run time.

Since `apptainer` is not on the login PATH, the venv route is the likely one. The image is therefore an optional
download, and the bundle itself is small.

## The commands, in order

**1. Get the bundle onto ARC.** Pack `vc_arc_bundle.tar` from this directory (the files listed under *Files*,
under `vc_arc/bundle/`), record its sha256, and copy it to `$DATA` on the ARC login node by any route you have
(for example `scp` or `rsync`). For the apptainer route, copy `villa.sif` to `$DATA/vc_arc/` the same way.

**2. ARC login node: unpack the bundle (about 5 MB).**
```sh
cd $DATA && sha256sum vc_arc_bundle.tar && tar -xf vc_arc_bundle.tar
```
Expected: the sha256 printed equals the one you recorded when you packed the bundle, and
`$DATA/vc_arc/bundle/` exists.

**3. ARC login node: set up (one time; 10–20 minutes, mostly downloads).**
```sh
bash $DATA/vc_arc/bundle/setup.sh
```
For the apptainer route, `villa.sif` must be in `$DATA/vc_arc/` (step 1), or pass a URL you can download it from:
`SIF_URL='<URL of your villa.sif>' bash $DATA/vc_arc/bundle/setup.sh`.

Expected lines:
- `bundle files ok`, then `patch zips ok`. It downloads Stevens' two public zips (2 GB) and checks their sha256.
- `villa source ok (f4570bf…)`.
- A route message.
- venv route: `venv imports ok 2.11.0+cu128 12.8`. apptainer route: `image imports ok 2.11.0+cu130`.
- `route recorded: route=… driver_min=…`.
- `inputs ok=15 bad=0 pending=3 …` and `READY FOR test_job.sh ONLY`.
- Last line: **`SETUP OK`**, or `SETUP FAILED: <reason>`.

**4. ARC: test job (10 minutes at most).**
```sh
cd $DATA/vc_arc && sbatch bundle/test_job.sh
```
Expected: `Submitted batch job NNN`. `vc_arc_test_NNN.out` should then contain, in order:
- the H100's name, memory and driver version;
- `cuda ok 2.11.0+cu128 12.8 NVIDIA H100 …` (venv route);
- `{"patches": 100, …}` and `staged in …s`;
- `fit exit 0 completed_iterations=50`;
- `DONE: steps=50 … route=…`;
- **`TEST JOB PASS`**.

If it stays pending with `ReqNodeNotAvail` because `devel` has no H100, change `--partition=devel` to `short` in
`bundle/test_job.sh` and resubmit.

**5. ARC login node: add SessA-12's whole-scroll files once they exist.** Copy `whole_scroll.tar` to `$DATA/vc_arc` first.
```sh
cd $DATA/vc_arc && tar -xf whole_scroll.tar && bash bundle/stage.sh
```
Expected: `ALL 18 INPUTS OK: ready for test_job.sh, arm_a.sh, arm_b.sh`. The updated `INPUTS.sha256` ships inside
`whole_scroll.tar`.

**6. ARC: submit both arms.**
```sh
cd $DATA/vc_arc && sbatch bundle/arm_b.sh && sbatch bundle/arm_a.sh
```
Expected: two `Submitted batch job NNN` lines.
- Progress: `squeue -u $USER`, and `cat $DATA/vc_arc/out/arm_*/progress.txt` (completed steps).
- Each log `vc_arc_arm_x_NNN.out` ends with either `DONE: steps=30000 …` or `NOT DONE (k / 30000). Resubmit the same
  script`.
- For the second case, run `sbatch bundle/arm_x.sh` again. It resumes from the newest checkpoint.

**7. ARC: pack the results.**
```sh
bash $DATA/vc_arc/bundle/pack_outputs.sh
```
Expected: `arm_a: <size>  <sha256>  vc_arc_arm_a.tar`, the same for arm_b, then `packed 2 arm(s)`. The tars are in
`$DATA/vc_arc/upload/`.

**8. Copy the results off ARC.** rsync `$DATA/vc_arc/upload/` to your own machine.

## What each job does
- **Setup.** `run_arm.sh` reads `route.txt` and loads any modules `setup.sh` recorded. It checks the driver
  (≥ 525 for the venv's CUDA 12.8, ≥ 580 for the image) and that CUDA works.
- **Staging.** It unpacks the zips to `$SCRATCH`, one folder per patch id. It refuses to run if a constraint names a
  patch with no folder, because villa would otherwise silently re-link it.
- **Fit.** It runs villa's unchanged `fit_spiral.py`:
  - z [496, 11,008), 30,000 steps;
  - CT-derived inputs off;
  - winding constraints on in arm (a) only, exactly as in SessB.
- **Checkpoints.** villa autosaves every 1,000 steps on scratch. Every 2,000th step is copied to
  `$DATA/vc_arc/out/<arm>/ckpt/`, keeping the newest 3. 15 minutes before the time limit, the job also copies the
  latest autosave.
- **Caches.** villa's derived-patch cache and the triton kernel cache persist in `$DATA/vc_arc/cache/<arm>/`, so a
  resubmitted job skips the cold start.
- **Finish.** It writes `final.ckpt` and `DONE`.

## Expected cost (projection from SessB, not a measurement)
- Slab on an L4: 0.114 s/step, 2.8 GB GPU memory, GPU about 20 % busy.
- Whole scroll: 13.7× the per-step samples. That projects to 3–13 L4-hours per arm and 12–25 GB of GPU memory; an H100
  should be faster.
- The first job of each arm also builds villa's derived-patch cache (estimated at about 1 hour for 56,968 patches).
- So expect 1 or 2 twelve-hour submissions per arm.

## Driver
- venv route: CUDA 12.8 wheels, driver ≥ 525 (≥ 570 recommended).
- apptainer route: driver ≥ 580.
- `run_arm.sh` stops with a clear message if the driver is too old. The apptainer route can also be rebuilt with the
  exact CUDA 12.8 lock from `villa_spiral.def` on any Linux machine with internet (`villa_src.tar` must sit beside it).
  Images cannot be built on ARC.

## Files (`bundle/`)
- `setup.sh`, `stage.sh`, `INPUTS.sha256`: setup and checks. Paths in `INPUTS.sha256` are relative to `$DATA/vc_arc`.
- `test_job.sh`, `arm_a.sh`, `arm_b.sh`, `run_arm.sh`: the Slurm scripts.
- `make_dataset.py`, `ckpt_iter.py`, `run_fit.py`: helpers.
- `pack_outputs.sh`: output packing.
- `villa_src.tar`: villa at f4570bf; `spiral-fitting/` and `vesuvius/src/vc3d_fiber_format/` only.
- `villa_spiral.def`, `build_sif_here.sh`, `BUILD_RECORD.json`, `FREEZE.txt`: how the optional image was built.
- `devel/`: the slab-2 umbilicus and 100 patch ids for the test job.
- `whole_scroll/`: SessA-12's files, once produced.

## Redo fits a2, b2 and c (Scroll 4)

- **a2/b2** = `run_arm.sh` patched by `patch_initdr.sh` (`arm_a2.sh`, `arm_b2.sh`; tranche `tranche_s4_cap/params.env`: NUM_WINDINGS=80, INIT_DR=32; `stage_cap.sh` checks it).
- **c** = additionally patched by `patch_abs.sh`, with `abs_winding.json` from the index (`arm_c.sh`; `stage_c.sh` and `check_abs_winding.py` check it). `abs_winding.json` itself is not in this repository.

