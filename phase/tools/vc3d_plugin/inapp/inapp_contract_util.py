"""Helpers shared by the in-app harnesses."""
import subprocess


def dock_rows_y(png):
    """y of the Sheet-check dock's first two rows: 4 and 18 px below the bottom of its title bar
    (colour 205,210,240 at x=1250). Robust to banners that shift the layout."""
    txt = subprocess.run(["convert", png, "-crop", "1x400+1250+0", "txt:-"], capture_output=True, text=True, check=True).stdout
    ys = [int(l.split(",")[1].split(":")[0]) for l in txt.splitlines()[1:] if "(205,210,240)" in l.replace(" ", "")]
    if not ys:
        raise SystemExit("dock title bar not found in " + png)
    end = ys[0]
    while end + 1 in ys:
        end += 1
    return end + 4, end + 18
