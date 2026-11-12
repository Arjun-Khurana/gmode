"""Full-vectorial finite-difference eigenmode solver on a Yee grid with PML.

With fields ~ exp(i*(neff*k0*z - omega*t)), coordinates scaled by k0 and
H scaled by eta0, Maxwell's curl equations reduce to

    neff [Ex, Ey] = P [Hx, Hy]        neff [Hx, Hy] = Q [Ex, Ey]

    P = [[ -Dxf ez^-1 Dyb,      Dxf ez^-1 Dxb + 1 ],
         [ -Dyf ez^-1 Dyb - 1,  Dyf ez^-1 Dxb     ]]
    Q = [[  Dxb Dyf,            -Dxb Dxf - ey     ],
         [  Dyb Dyf + ex,       -Dyb Dxf          ]]

so P Q e = neff^2 e, solved by shift-invert around the target index.
PML enters as complex coordinate stretching of the derivative operators.
"""
import time

import numpy as np
import pymetis
import scipy.sparse as sp
from scipy.sparse.linalg import LinearOperator, eigs, splu

from ..grid import Axis, Grid, build_axis, rasterize
from ..project import Project
from ..results import Mode, ModeSet

# relative accuracy of neff^2; far below discretization error, and ~25% fewer
# Arnoldi iterations than ARPACK's machine-precision default
_EIG_TOL = 1e-10


def _derivatives(axis: Axis):
    """Forward (nodes -> half points) and backward (half points -> nodes) 1D derivatives."""
    n = axis.n
    fwd = sp.diags([-np.ones(n), np.ones(n - 1)], [0, 1], shape=(n, n), format="lil", dtype=complex)
    bwd = sp.diags([np.ones(n), -np.ones(n - 1)], [0, -1], shape=(n, n), format="lil", dtype=complex)

    if axis.upper == "periodic":
        fwd[n - 1, 0] += 1
    elif axis.upper == "pmc":
        # tangential E even about the wall -> no change across the last half cell
        fwd[n - 1, :] = 0
    # pec / pml: tangential E is zero beyond the last node (zero padding)

    if axis.lower == "periodic":
        bwd[0, n - 1] -= 1
    elif axis.lower == "pec":
        # wall on node 0: tangential H even across it
        bwd[0, :] = 0
    elif axis.lower == "pmc":
        # wall on node 0: tangential H odd across it
        bwd[0, 0] = 2
    # pml: tangential H is zero half a cell before node 0 (zero padding)

    fwd = sp.diags(1 / (axis.s_half * axis.d_fwd)) @ fwd.tocsr()
    bwd = sp.diags(1 / (axis.s_nodes * axis.d_bwd)) @ bwd.tocsr()
    return fwd, bwd


def _shift_invert(A, sigma) -> LinearOperator:
    """(A - sigma I)^-1 via SuperLU, with a METIS nested-dissection ordering.

    On grid operators nested dissection gives about half the fill of SuperLU's
    default COLAMD ordering, which roughly halves factor and solve times.
    """
    n = A.shape[0]
    M = (A - sigma * sp.identity(n, format="csc")).tocsc()
    G = (abs(M) + abs(M.T)).tocsr()
    G.setdiag(0)
    G.eliminate_zeros()
    perm = np.asarray(pymetis.nested_dissection(pymetis.CSRAdjacency(G.indptr, G.indices))[0])
    inv = np.empty_like(perm)
    inv[perm] = np.arange(n)
    lu = splu(M[perm][:, perm].tocsc(), permc_spec="NATURAL")
    return LinearOperator((n, n), matvec=lambda b: lu.solve(b[perm])[inv], dtype=M.dtype)


def _pec_masks(grid: Grid):
    """Zero tangential E and normal H on PEC walls lying on node 0."""
    nx, ny = grid.shape
    ex, ey = np.ones((nx, ny)), np.ones((nx, ny))
    hx, hy = np.ones((nx, ny)), np.ones((nx, ny))
    if grid.x.lower == "pec":
        ey[0, :] = 0
        hx[0, :] = 0
    if grid.y.lower == "pec":
        ex[:, 0] = 0
        hy[:, 0] = 0
    e_mask = np.concatenate([ex.ravel(), ey.ravel()])
    h_mask = np.concatenate([hx.ravel(), hy.ravel()])
    return e_mask, h_mask


def _pad(a, axis: int, ax: Axis, side: str):
    """Pad one ghost layer on `side` ("lo"/"hi") consistent with the boundary condition."""
    width = [(0, 0)] * a.ndim
    width[axis] = (1, 0) if side == "lo" else (0, 1)
    bc = ax.lower if side == "lo" else ax.upper
    if bc == "periodic":
        return np.pad(a, width, mode="wrap")
    if bc == "pmc" and side == "hi":
        return np.pad(a, width, mode="edge")
    return np.pad(a, width)


def _to_half(a, axis: int, ax: Axis):
    """Average node-located samples onto half points along `axis`."""
    p = _pad(a, axis, ax, "hi")
    lo = np.take(p, range(0, a.shape[axis]), axis=axis)
    hi = np.take(p, range(1, a.shape[axis] + 1), axis=axis)
    return 0.5 * (lo + hi)


def _mirror(a, axis: int, sign: float):
    return np.concatenate([sign * np.flip(a, axis=axis), a], axis=axis)


# mirror parity of (Ex, Ey, Ez, Hx, Hy, Hz) across a symmetry plane normal to x / y
_PARITY = {
    ("x", "pec"): (1, -1, -1, -1, 1, 1),
    ("x", "pmc"): (-1, 1, 1, 1, -1, -1),
    ("y", "pec"): (-1, 1, -1, 1, -1, 1),
    ("y", "pmc"): (1, -1, 1, -1, 1, -1),
}


class FDESolver:
    name = "fde"

    def solve(self, project: Project) -> ModeSet:
        t0 = time.perf_counter()
        grid = Grid(build_axis(project, "x"), build_axis(project, "y"))
        nx, ny = grid.shape
        N = nx * ny
        k0 = 2 * np.pi / project.wavelength

        eps_x, eps_y, eps_z = rasterize(project, grid)

        dxf, dxb = _derivatives(grid.x)
        dyf, dyb = _derivatives(grid.y)
        Ix, Iy = sp.identity(nx), sp.identity(ny)
        Dxf, Dxb = sp.kron(dxf, Iy) / k0, sp.kron(dxb, Iy) / k0
        Dyf, Dyb = sp.kron(Ix, dyf) / k0, sp.kron(Ix, dyb) / k0

        I = sp.identity(N)
        iez = sp.diags(1 / eps_z.ravel())
        P = sp.bmat([[-Dxf @ iez @ Dyb, Dxf @ iez @ Dxb + I],
                     [-Dyf @ iez @ Dyb - I, Dyf @ iez @ Dxb]])
        Q = sp.bmat([[Dxb @ Dyf, -Dxb @ Dxf - sp.diags(eps_y.ravel())],
                     [Dyb @ Dyf + sp.diags(eps_x.ravel()), -Dyb @ Dxf]])

        e_mask, h_mask = _pec_masks(grid)
        Me, Mh = sp.diags(e_mask), sp.diags(h_mask)
        P = Me @ P @ Mh
        Q = Mh @ Q @ Me
        A = (P @ Q).tocsc()
        if not np.any(A.data.imag):
            # lossless without PML: real arithmetic makes the LU several times cheaper
            A = A.real

        target = project.solver.target_neff
        if target is None:
            target = np.sqrt(np.max(np.real(eps_z)))
        k = min(project.solver.num_modes, 2 * N - 2)
        ncv = min(max(2 * k + 1, k + 20), 2 * N)
        sigma = target**2
        vals, vecs = eigs(A, k=k, sigma=sigma, OPinv=_shift_invert(A, sigma), ncv=ncv,
                          v0=np.ones(2 * N, dtype=A.dtype), tol=_EIG_TOL)
        t_eig = time.perf_counter() - t0

        neffs = np.sqrt(vals.astype(complex))
        order = np.argsort(-neffs.real)
        modes = [self._fields(project, grid, eps_z, Q, Dxf, Dxb, Dyf, Dyb, neffs[i], vecs[:, i])
                 for i in order]
        for m in modes:
            m.meta.update(backend="fde", grid_shape=grid.shape, solve_time=t_eig)
        return ModeSet(modes, project.model_copy(deep=True), "fde")

    def _fields(self, project, grid, eps_z, Q, Dxf, Dxb, Dyf, Dyb, neff, e):
        nx, ny = grid.shape
        N = nx * ny
        h = Q @ e / neff
        ex, ey = e[:N], e[N:]
        hx, hy = h[:N], h[N:]
        ez = 1j * (Dxb @ hy - Dyb @ hx) / eps_z.ravel()
        hz = -1j * (Dxf @ ey - Dyf @ ex)
        f = [a.reshape(nx, ny) for a in (ex, ey, ez, hx, hy, hz)]

        # interpolate everything to cell centres (xh, yh)
        gx, gy = grid.x, grid.y
        Ex = _to_half(f[0], 1, gy)
        Ey = _to_half(f[1], 0, gx)
        Ez = _to_half(_to_half(f[2], 0, gx), 1, gy)
        Hx = _to_half(f[3], 0, gx)
        Hy = _to_half(f[4], 1, gy)
        Hz = f[5]
        comps = [Ex, Ey, Ez, Hx, Hy, Hz]

        x, y = gx.half, gy.half
        dx, dy = gx.d_fwd, gy.d_fwd
        b = project.boundaries
        for ax, axis_idx, sym in (("x", 0, b.x_symmetry), ("y", 1, b.y_symmetry)):
            if sym == "none":
                continue
            c = project.domain.center[axis_idx]
            comps = [_mirror(a, axis_idx, s) for a, s in zip(comps, _PARITY[(ax, sym)])]
            if ax == "x":
                x, dx = np.concatenate([2 * c - x[::-1], x]), np.concatenate([dx[::-1], dx])
            else:
                y, dy = np.concatenate([2 * c - y[::-1], y]), np.concatenate([dy[::-1], dy])

        eps = project.eps_at(x[:, None], y[None, :])
        return Mode(neff=complex(neff), wavelength=project.wavelength, x=x, y=y, dx=dx, dy=dy,
                    E=np.array(comps[:3]), H=np.array(comps[3:]), eps=eps).normalize()
