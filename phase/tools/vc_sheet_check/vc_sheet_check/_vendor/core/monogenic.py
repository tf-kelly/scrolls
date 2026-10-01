"""Monogenic signal of a sheet stack: local phase, amplitude, normal, frequency.

Band-pass: isotropic log-Gabor centred on 1/period_px with a full width at
half maximum of `bandwidth_oct` octaves.  With e the band-passed (even) signal
and q = R e its Riesz transform (odd, a 3-vector), a locally simple signal
A cos(phi) with unit normal n gives

    e = A cos phi,  q = A sin phi n,
    grad e = -A sin phi (2 pi k) n,   J_q = dq_j/dx_i = A cos phi (2 pi k) n n^T

so that, without any sign choice,

    amp   = sqrt(e^2 + |q|^2)                         = A
    kappa = sqrt(|grad e|^2 + |J_q|_F^2) / (2 pi amp)  = k   (cycles/voxel)
    T     = q q^T + e J_q / (2 pi kappa)               = A^2 n n^T

(using e J_q = A^2 cos^2 phi (2 pi kappa) n n^T; this linear form needs no
product of J_q with itself and is built in place).  The normal is the
principal eigenvector of T, which (unlike q/|q|) does not
vanish on the sheet centre.  Its sign is then set to the sign of q along it,
so normal_unit is the direction of increasing phase whenever psi_unoriented
is read as a signed phase; orient() uses this pairing.
"""
from __future__ import annotations

import numpy as np
import scipy.fft as sfft

from ._chunks import iter_cores, make_out, read_block, spatial_shape

_WORKERS = -1


def _freq_grids(shape):
    fz = np.fft.fftfreq(shape[0]).astype(np.float32)[:, None, None]
    fy = np.fft.fftfreq(shape[1]).astype(np.float32)[None, :, None]
    fx = np.fft.rfftfreq(shape[2]).astype(np.float32)[None, None, :]
    return fz, fy, fx


def _log_gabor(shape, period_px, bandwidth_oct):
    fz, fy, fx = _freq_grids(shape)
    f = np.sqrt(fz * fz + fy * fy + fx * fx)
    f0 = 1.0 / period_px
    s = bandwidth_oct * np.log(2.0) / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    with np.errstate(divide="ignore"):
        H = np.exp(-0.5 * (np.log(f / f0) / s) ** 2)
    H[0, 0, 0] = 0.0
    fs = np.where(f > 0, f, 1.0)
    return H.astype(np.float32), (fz, fy, fx), fs


_IDX = [(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]


def _sym_matvec(T, v):
    """T given as 6 unique components (xx order of _IDX); v (3,...)."""
    return np.stack([T[0] * v[0] + T[3] * v[1] + T[4] * v[2],
                     T[3] * v[0] + T[1] * v[1] + T[5] * v[2],
                     T[4] * v[0] + T[5] * v[1] + T[2] * v[2]])


def _principal_vector(T, iters=6):
    """Eigenvector of the largest eigenvalue by power iteration, started from
    the column with the largest diagonal entry."""
    col = np.argmax(np.stack([T[0], T[1], T[2]]), axis=0)
    rows = [(0, 3, 4), (3, 1, 5), (4, 5, 2)]
    v = np.stack([np.choose(col, [T[rows[0][a]], T[rows[1][a]], T[rows[2][a]]])
                  for a in range(3)])
    tiny = np.float32(1e-20)
    for _ in range(iters):
        v = _sym_matvec(T, v)
        v /= np.maximum(np.linalg.norm(v, axis=0), tiny)
    return v


def halo_for(period_px):
    return int(np.ceil(3.0 * period_px)) + 2


def _block_monogenic(x, period_px, bandwidth_oct, inner):
    """All monogenic quantities on one padded block, cropped to `inner`."""
    shape = x.shape
    H, (fz, fy, fx), fs = _log_gabor(shape, period_px, bandwidth_oct)
    G = sfft.rfftn(x, workers=_WORKERS)
    G *= H
    del H
    f = (fz, fy, fx)

    def inv(mult):
        return sfft.irfftn(G * mult, s=shape, workers=_WORKERS)[inner].astype(np.float32)

    e = inv(np.float32(1.0))
    q = np.stack([inv(-1j * (fi / fs)) for fi in f])                  # Riesz, odd
    qn2 = np.sum(q * q, axis=0)
    amp = np.sqrt(e * e + qn2)
    psi_u = (np.arctan2(np.sqrt(qn2), e) / (2 * np.pi)).astype(np.float32)   # [0, 0.5]
    del qn2
    acc = np.zeros_like(e)                                           # |grad e|^2 + |J|_F^2
    for fi in f:
        gi = inv(2j * np.pi * fi)
        acc += gi * gi
    del gi
    # symmetric Jacobian of q: d q_j / d x_i = irfft(G * 2 pi f_i f_j / |f|)
    J = np.empty((6,) + e.shape, np.float32)
    for k, (i, j) in enumerate(_IDX):
        J[k] = inv((2 * np.pi) * f[i] * f[j] / fs)
        acc += (1.0 if i == j else 2.0) * J[k] * J[k]
    del G
    tiny = np.float32(1e-12)
    kappa = (np.sqrt(acc) / (2 * np.pi * np.maximum(amp, tiny))).astype(np.float32)
    del acc
    # T * (2 pi kappa) = e J + (2 pi kappa) q q^T   (= 2 pi kappa A^2 n n^T for a
    # simple signal, since J = e (2 pi kappa) n n^T); built in place over J.
    w = (2 * np.pi) * kappa
    J *= e
    for k, (i, j) in enumerate(_IDX):
        J[k] += w * q[i] * q[j]
    del w
    v = _principal_vector(J)
    del J
    sgn = np.sign(np.sum(v * q, axis=0))
    sgn[sgn == 0] = 1
    normal = (v * sgn).astype(np.float32)
    return psi_u, amp.astype(np.float32), normal, kappa


def monogenic(vol, period_px, bandwidth_oct=1.0, chunk=128, out=None, halo=None):
    """Returns psi_unoriented [0, 0.5] (turns), amp, normal_unit (3,...),
    kappa (cycles/voxel).  normal_unit carries the sign of the odd part:
    psi_signed = psi_unoriented if normal_unit points along the chosen
    orientation, else 1 - psi_unoriented (see orient)."""
    shape = spatial_shape(vol)
    halo = halo_for(period_px) if halo is None else halo
    psi_u = make_out(out, "psi_unoriented", shape, np.float32, chunk)
    amp = make_out(out, "amp", shape, np.float32, chunk)
    nrm = make_out(out, "normal_unit", (3,) + shape, np.float32, chunk)
    kap = make_out(out, "kappa", shape, np.float32, chunk)
    for core in iter_cores(shape, chunk):
        x, inner = read_block(vol, core, halo)
        x = x.astype(np.float32, copy=False)
        p, a, n, k = _block_monogenic(x, period_px, bandwidth_oct, inner)
        del x
        psi_u[core] = p
        amp[core] = a
        nrm[(slice(None),) + core] = n
        kap[core] = k
    return psi_u, amp, nrm, kap
