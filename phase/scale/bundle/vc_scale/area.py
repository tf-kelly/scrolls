"""Patch areas from tifxyz grids (level-0 voxels -> cm^2)."""
import numpy as np

from .surf import cell_area_vox2


def quad_centres(zyx):
    return 0.25 * (zyx[:-1, :-1] + zyx[:-1, 1:] + zyx[1:, :-1] + zyx[1:, 1:])


def quad_areas(zyx):
    """True 3-D quad areas (vox^2), NaN for quads with an invalid corner."""
    return cell_area_vox2(zyx)


def vox2_to_cm2(a, voxel_um):
    return a * (voxel_um * 1e-4) ** 2
