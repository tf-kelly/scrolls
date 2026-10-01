# SessD: VC3D "Tools → Sheet check" (thin plugin)

VC3D wiring for contract-v1 sheet-check outputs (`phase/tools/CONTRACT.md` §4.1–4.2). The plugin:
- runs `vc_sheet_check` as a subprocess on the active segment and the current volume;
- loads its overlay zarr as VC3D's overlay layer;
- lists `report.json` clusters in a dock, with jump-to.

**All analysis belongs to the CLI. The plugin does no analysis.** Target: `ScrollPrize/villa` `f4570bf`
(2026-09-26).

## Status in this release (join mode, SessA instruction; see `JOIN.md`)
- **Join mode runs from the plugin's own menu:** **Tools → Sheet check (joins)** builds the checker's region (join)
  call itself from a small join spec, with no adapter. `run_join_test.sh` drives it headlessly on fixture region A.
- **Single-patch (segment) mode does not complete from the menu in this release** (see below).

## Status (SessD-5)
- **Segment mode gets an axis.** The plugin passes the project's umbilicus, found by VC3D's own resolver, as
  `--axis-file`. With none, it refuses to launch and gives a one-line reason. All three paths were tested in-app
  against SessA's real CLI.
- **The real segment check still does not complete from the menu.** SessA reads neither villa's `umbilicus.json` nor
  A5.3's headered CSV, and it wants `--scan-shape` for a local volume (R11). Run by hand with both, it succeeds.
- **Level 1:** overlay and CT shift together (a planted CT feature; −0.25 px residual from trilinear vs nearest). The
  scans' pyramids are a 2× mean; the overlay's is a 2× max, with the same centre.
- **Controls show CT:** on a uint8 fixture CT, 36/36 controls are gray and 48/48 xy pixels equal the CT.
- **uint16 one-byte read confirmed** by a direct sampler test (Draft 3).
- **Fixed:** the outside tag now uses A10.2's `overlay_region`.

## Status (SessD-3: real checker at <branch> da5da56)
- **Real checker end to end.** SessA's fixture run passes the contract validator. The plugin loads SessA's overlay without
  the guard firing, the probe on it gives 16/16, the dock shows 51 clusters, and 3 jumps inside the region are exact.
  Region mode was invoked through an adapter.
- **The menu's standard (A4.2) call cannot run SessA's segment mode:** no axis file (R9).
- **Level 1** is drawn half a level-0 voxel off; this is sub-pixel at natural zoom (R10).
- **The xz viewer** is tested (60/60).

## Status (SessD-2, fixture v1.1, contract Amendments 3–4)
- **Built and run in VC3D.** In-app tests use a **stub** checker. The real `vc_sheet_check` was not run; integrator has not
  said SessA has landed.
- **Overlay placement is voxel-exact.** Shown by a pixel probe for Zarr v2, Zarr v3 and the contract's reference
  writer.
- **Translated overlays are refused** by the plugin's guard. VC3D's local reader ignores OME translations and draws
  the array offset by the region origin, silently.
- **Project file:** one overlay entry per segment; dead entries are removed.
- **Bridge script:** `bridge_script/` is a **development and test harness, not a user deliverable** (see below).
- **(f), the end-to-end check on SessA's overlay, is prepared** and waits for SessA's merge.

## Files
| path | what |
|---|---|
| `villa_sheet_check.patch` | Whole change against villa `f4570bf`: 3 upstream files (+115 lines) and 4 new files in `apps/VC3D/sheet_check/`. Applies cleanly; verified to reproduce the tested tree byte-for-byte. |
| `villa_hook.patch` | The upstream-file part of the above only (menu hook, CMake). |
| `src/` | The new files, for reading and for the unit test: `SheetCheckCore.*` (Qt Core only), `SheetCheckController.*`, `test_sheet_check_core.cpp`. |
| `build_vc3d.sh` | Clone/checkout the pin, apply the patch, build `VC3D` (`--apt` installs dependencies). |
| `run_unit_tests.sh` | Non-GUI tests: the C++ core and the bridge script's Python core against the golden v1.1 `report.json`, and the view writer. |
| `overlay_vc3d_view.py` | Relocates a translated region zarr to the scan frame. Superseded for overlays by Amendment 4; still used to open the fixture's `ct.zarr` as the test base volume. |
| `real/` | `region_adapter.sh` (runs SessA's own region-A command for the plugin), `run_real.sh` (the in-app test against SessA's real CLI), and `run_axis.sh`/`axis_test.py` (umbilicus cases A/B/C against SessA's real CLI). |
| `probe/` | Placement probe: `make_probe.py` (synthetic v2/v3/region), `probe_existing.py` (any full-frame overlay, symlinked not copied; `--within` box), `run_probe.sh`, `eval_controls.py` (controls = CT). |
| `bridge_script/` | **Development and test harness, not a user deliverable.** `sheet_check_bridge.py` drives VC3D's agent bridge; it has unit and in-app tests. |
| `inapp/` | Xvfb in-app tests: `build_inapp_fixture.sh` (also writes `cfx/umbilicus.json` and the uint8 CT via `make_ct_u8.py`), `run_contract.sh` (modes golden, legacy_translation, fail, invalid), `run_project_entries.sh`, and **`stub_contract_cli` (a stub, not the real CLI)**. |

## Reproduce
```bash
T=phase/tools/vc3d_plugin; PY=python3          # PY must satisfy phase/tools/requirements.txt (zarr==2.18.7)
$T/build_vc3d.sh /tmp/villa --apt                # 10 min on 4 cores
VC3D=/tmp/villa/volume-cartographer/build/bin/VC3D
$T/inapp/build_inapp_fixture.sh /tmp/w $PY
$T/run_unit_tests.sh /tmp/w/golden/A $PY
for m in golden legacy_translation fail invalid; do $T/inapp/run_contract.sh $VC3D /tmp/w /tmp/run_$m $m $PY; done
$T/inapp/run_project_entries.sh $VC3D /tmp/w /tmp/run_pe $PY
for m in golden legacy_translation fail invalid; do $T/bridge_script/run_bridge_test.sh $VC3D /tmp/w /tmp/br_$m $m $PY; done
$PY $T/probe/make_probe.py /tmp/probe            # needs zarr>=3 (create_array API); any venv with zarr 3
for v in v2 v3 region; do $T/probe/run_probe.sh $VC3D /tmp/w /tmp/probe /tmp/pr_$v $v; done
# SessD-5: controls over the uint8 CT; golden v1.4 targets restricted to the fixture CT crop
$PY $T/probe/probe_existing.py /tmp/w/golden/A/overlay.zarr /tmp/probe/golden_v14 --within 4224 2560 640 4608 2944 1024
for v in v2 golden_v14; do VP_BASE_VOLUME=ct_A_u8.zarr VP_SHOW_XZ=1 $T/probe/run_probe.sh $VC3D /tmp/w /tmp/probe /tmp/pr5_$v $v
  $PY $T/probe/eval_controls.py /tmp/pr5_$v/probe_result.json /tmp/w/cfx/volumes/ct_A_u8.zarr; done
for c in A B C; do VP_BASE_VOLUME=ct_A_u8.zarr $T/real/run_axis.sh $VC3D /tmp/w /tmp/ax_$c $c <SessA venv>/bin phase/tools/axis/pherc1667_x3slab2_axis.csv; done
```
- The in-app tests click the menu at a fixed screen position (Xvfb 1920×1080, no window manager).
- They find the dock rows from the dock title bar's colour.
- Every run checks its own results and exits non-zero on a mismatch.

## Disk space and volume type (SessD-5)

**VC3D stops downloading remote chunks below 20 GiB free disk.**
- The setting is `perf/remote_cache_min_free_gib`, default 20 (`apps/VC3D/VCSettings.hpp:221`). It applies to every
  remote zarr cache in the cache directory, not only this plugin's volumes.
- Below the floor VC3D keeps running but fetches nothing new, so remote slices stay black or partial. This is easy
  to mistake for a placement or overlay bug.
- **To lower it**, pick one:
  - *Settings → "Minimum free disk space (GiB)"*, applied immediately; 0 turns the reserve off;
  - or in `VC3D.ini` (in `VC3D_CONFIG_DIR` when that is set):
    ```ini
    [perf]
    remote_cache_min_free_gib=4
    remote_cache_max_gib=3
    ```
    `remote_cache_max_gib` caps the cache itself (0 = unlimited, the default), so a small floor does not let the cache
    fill the disk.
- Local volumes, such as the overlay the plugin writes or a local CT copy, get no persistent cache
  (`core/src/Volume.cpp:1667`), so the floor does not apply to them.

**Use uint8 volumes as the base volume.**
- At villa `f4570bf` the slice viewers draw uint16 volumes as noise. The plane sampler reads one byte at the
  element offset.
- The overlay is uint8 and is unaffected. The problem is only the CT behind it.
- For the fixture, `inapp/make_ct_u8.py` writes a uint8 copy (`ct_A_u8.zarr`; its 16→8-bit window is recorded in its
  `meta.json`).

## Why the bridge script is a harness, not a deliverable (SessD-3)
1. **Off by default.**
   - The agent bridge is compiled into every VC3D build, but it runs only when VC3D is started with
     `--agent-bridge` (`apps/VC3D/VCAppMain.cpp:449-458`).
   - A normal user launch has no socket to talk to.
2. **Unstable protocol.**
   - The bridge SPEC says only "Status: current protocol reference. Protocol version 2".
   - Version 2 already removed fields, the bridge is two months old (#1179), and there is no stability promise.
   - The script refuses any protocol other than 2, so the next bump breaks it.
3. **GUI-click focus and no detach.**
   - The bridge has no call that sets the focus. The script moves it with two ctrl-clicks (xy, then yz), which relies
     on click semantics, not an API.
   - The bridge also has no call that removes a volume entry, so every run appends one to the project file. The
     plugin replaces its entry instead (SessD-2 (c)).

The script stays because it drives the same checker → overlay → jump path without a rebuild, which is what the
in-app tests need.
