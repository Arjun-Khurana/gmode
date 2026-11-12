"""MPB backend (plane-wave expansion, periodic cell, lossless materials only).

MPB is non-dispersive, but each solve is at a single wavelength, so materials are
evaluated there. The group index still includes material dispersion, because it
is computed from the fields with d(omega*eps)/d(omega).

Needs the meep python package, which is not on PyPI: install gmode into an
environment that already has meep (e.g. `uv pip install -e . --python <meep venv>`).
"""
import time
import warnings

import numpy as np

from ..project import Project
from ..results import Mode, ModeSet


class MPBSolver:
    name = "mpb"

    def solve(self, project: Project) -> ModeSet:
        try:
            import meep as mp
            from meep import mpb
        except ImportError as e:
            raise RuntimeError("the MPB backend needs the meep python package") from e

        self._check(project)
        wl = project.wavelength
        omega = 1 / wl
        (cx, cy), (Lx, Ly) = project.domain.center, project.domain.size
        resolution = 1 / min(project.mesh.dx, project.mesh.dy)

        eps = {k: float(np.real(project.materials[k].eps(wl))) for k in project._used_materials()}

        def medium(name):
            return mp.Medium(epsilon=eps[name])

        geometry = []
        for s in project.structures:
            if s.type == "rectangle":
                geometry.append(mp.Block(center=mp.Vector3(s.center[0] - cx, s.center[1] - cy),
                                         size=mp.Vector3(*s.size, mp.inf), material=medium(s.material)))
            elif s.type == "circle":
                geometry.append(mp.Cylinder(center=mp.Vector3(s.center[0] - cx, s.center[1] - cy),
                                            radius=s.radius, height=mp.inf, material=medium(s.material)))
            else:
                verts = [mp.Vector3(x - cx, y - cy) for x, y in s.vertices]
                geometry.append(mp.Prism(verts, height=mp.inf, material=medium(s.material)))

        ms = mpb.ModeSolver(
            geometry_lattice=mp.Lattice(size=mp.Vector3(Lx, Ly, 0)),
            geometry=geometry,
            default_material=medium(project.background),
            resolution=resolution,
            num_bands=project.solver.num_modes,
        )

        indices = [np.sqrt(eps[k]) for k in {project.background, *(s.material for s in project.structures)}]
        n_guess = project.solver.target_neff or 0.9 * max(indices)
        t0 = time.perf_counter()
        modes = []
        for band in range(1, project.solver.num_modes + 1):
            try:
                k = ms.find_k(mp.NO_PARITY, omega, band, band, mp.Vector3(z=1), 1e-8,
                              omega * n_guess, omega * 0.1, omega * max(indices))
            except ValueError:
                break  # no further band below this frequency in the k range
            E = np.asarray(ms.get_efield(band, bloch_phase=False))[:, :, 0, :]
            H = np.asarray(ms.get_hfield(band, bloch_phase=False))[:, :, 0, :]
            nx, ny = E.shape[:2]
            x = cx - Lx / 2 + Lx * np.arange(nx) / nx
            y = cy - Ly / 2 + Ly * np.arange(ny) / ny
            modes.append(Mode(
                neff=complex(k[0] / omega), wavelength=wl, x=x, y=y,
                dx=np.full(nx, Lx / nx), dy=np.full(ny, Ly / ny),
                E=np.moveaxis(E, -1, 0), H=np.moveaxis(H, -1, 0),
                eps=project.eps_at(x[:, None], y[None, :]),
                eps_group=project.group_eps_at(x[:, None], y[None, :]),
            ).normalize())
        for m in modes:
            m.meta.update(backend="mpb", grid_shape=m.eps.shape, solve_time=time.perf_counter() - t0)
        return ModeSet(modes, project.model_copy(deep=True), "mpb")

    @staticmethod
    def _check(project: Project):
        if any(np.imag(project.materials[k].eps(project.wavelength)) != 0 for k in project._used_materials()):
            raise ValueError("MPB only supports lossless materials; use the fde backend")
        b = project.boundaries
        if {b.x_min, b.x_max, b.y_min, b.y_max} != {"periodic"}:
            warnings.warn("MPB uses periodic boundaries; the project's boundary conditions are ignored")
        if b.x_symmetry != "none" or b.y_symmetry != "none":
            warnings.warn("mirror symmetries are ignored by the MPB backend")
