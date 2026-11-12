"""Yee grid for the cross-section and permittivity rasterization.

Field locations in cell (i, j), with nodes at (x[i], y[j]) and half points at
(xh[i], yh[j]) = midpoints to the next node:

    Ex, Hy: (xh, y)    Ey, Hx: (x, yh)    Ez: (x, y)    Hz: (xh, yh)
"""
from dataclasses import dataclass

import numpy as np

from .project import Project

_CHUNK_POINTS = 4_000_000  # samples evaluated per rasterization chunk
_PML_REFLECTION = 1e-6  # target normal-incidence reflection for the default PML strength


@dataclass
class Axis:
    nodes: np.ndarray  # integer-point coordinates, length N
    end: float  # coordinate of the (excluded) node N; for periodic axes it is identified with nodes[0]
    lower: str  # boundary at nodes[0]: "pml", "pec", "pmc" or "periodic"
    upper: str  # boundary at `end`
    s_nodes: np.ndarray  # complex PML stretch factor at nodes
    s_half: np.ndarray  # ... and at half points

    @property
    def n(self) -> int:
        return len(self.nodes)

    @property
    def d_fwd(self) -> np.ndarray:
        """node[i] -> node[i+1] spacing (width of the cell centred on half point i)."""
        return np.diff(np.append(self.nodes, self.end))

    @property
    def half(self) -> np.ndarray:
        return self.nodes + self.d_fwd / 2

    @property
    def d_bwd(self) -> np.ndarray:
        """half[i-1] -> half[i] spacing (width of the cell centred on node i)."""
        h = self.half
        if self.lower == "periodic":
            prev = h[-1] - (self.end - self.nodes[0])
        else:
            prev = self.nodes[0] - self.d_fwd[0] / 2
        return np.diff(np.concatenate([[prev], h]))


def _pml_stretch(pos, inner_lo, inner_hi, thick_lo, thick_hi, sigma_lo, sigma_hi, order):
    s = np.ones(pos.shape, dtype=complex)
    if thick_lo > 0:
        u = np.clip((inner_lo - pos) / thick_lo, 0, None)
        s += 1j * sigma_lo * u**order
    if thick_hi > 0:
        u = np.clip((pos - inner_hi) / thick_hi, 0, None)
        s += 1j * sigma_hi * u**order
    return s


def _pml_sigma(project: Project, thickness: float, n_ref: float) -> float:
    """Peak of the stretch s = 1 + i*sigma*u^m (u = depth / thickness)."""
    b = project.boundaries
    if b.pml_sigma is not None:
        return b.pml_sigma
    k0 = 2 * np.pi / project.wavelength
    # normal-incidence round trip: exp(-2 n k0 sigma thickness / (m + 1)) = R
    return (b.pml_order + 1) * np.log(1 / _PML_REFLECTION) / (2 * n_ref * k0 * thickness)


def build_axis(project: Project, ax: str) -> Axis:
    b, m = project.boundaries, project.mesh
    i = "xy".index(ax)
    c, size = project.domain.center[i], project.domain.size[i]
    d = getattr(m, f"d{ax}")
    lower, upper = getattr(b, f"{ax}_min"), getattr(b, f"{ax}_max")
    sym = getattr(b, f"{ax}_symmetry")

    lo, hi = c - size / 2, c + size / 2
    if sym != "none":
        lo, lower = c, sym
    n = max(1, int(round((hi - lo) / d)))
    d = (hi - lo) / n

    n_lo = b.pml_layers if lower == "pml" else 0
    n_hi = b.pml_layers if upper == "pml" else 0
    nodes = lo + d * np.arange(-n_lo, n + n_hi)
    end = hi + n_hi * d

    n_ref = np.sqrt(np.real(project.materials[project.background].eps(project.wavelength)))
    sig_lo = _pml_sigma(project, n_lo * d, n_ref) if n_lo else 0.0
    sig_hi = _pml_sigma(project, n_hi * d, n_ref) if n_hi else 0.0
    args = (lo, hi, n_lo * d, n_hi * d, sig_lo, sig_hi, b.pml_order)
    s_nodes = _pml_stretch(nodes, *args)
    s_half = _pml_stretch(nodes + d / 2, *args)
    return Axis(nodes, end, lower, upper, s_nodes, s_half)


@dataclass
class Grid:
    x: Axis
    y: Axis

    @property
    def shape(self):
        return self.x.n, self.y.n


def _cell_bounds(axis: Axis, at_half: bool):
    if at_half:
        return axis.nodes, np.append(axis.nodes[1:], axis.end)
    h = axis.half
    return h - axis.d_bwd, h


def _average(project: Project, xb, yb, s: int, harmonic_axis):
    """Average eps over the cells xb x yb with s*s samples each.

    Interfaces normal to `harmonic_axis` ("x", "y" or None) are averaged
    harmonically (normal component of D continuous), all others arithmetically.
    """
    t = (np.arange(s) + 0.5) / s
    xs = xb[0][:, None] + (xb[1] - xb[0])[:, None] * t  # (Nx, s)
    ys = yb[0][:, None] + (yb[1] - yb[0])[:, None] * t  # (Ny, s)
    nx, ny = len(xs), len(ys)
    out = np.empty((nx, ny), dtype=complex)
    rows = max(1, _CHUNK_POINTS // (ny * s * s))
    for i0 in range(0, nx, rows):
        X = xs[i0 : i0 + rows, None, :, None]
        Y = ys[None, :, None, :]
        e = project.eps_at(X, Y)  # (rows, Ny, sx, sy)
        if harmonic_axis == "x":
            out[i0 : i0 + rows] = 1 / np.mean(1 / e.mean(axis=3), axis=2)
        elif harmonic_axis == "y":
            out[i0 : i0 + rows] = 1 / np.mean(1 / e.mean(axis=2), axis=2)
        else:
            out[i0 : i0 + rows] = e.mean(axis=(2, 3))
    return out


def rasterize(project: Project, grid: Grid):
    """Return (eps_x, eps_y, eps_z) at their Yee locations, each of shape grid.shape."""
    s = project.mesh.subpixel
    gx, gy = grid.x, grid.y
    eps_x = _average(project, _cell_bounds(gx, True), _cell_bounds(gy, False), s, "x")
    eps_y = _average(project, _cell_bounds(gx, False), _cell_bounds(gy, True), s, "y")
    eps_z = _average(project, _cell_bounds(gx, False), _cell_bounds(gy, False), s, None)
    return eps_x, eps_y, eps_z
