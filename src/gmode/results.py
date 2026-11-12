"""Backend-independent mode results.

Fields are stored on a common rectilinear grid of cell centres. H is scaled by
the free-space impedance (H_stored = eta0 * H), so E and H share units. Each
mode is normalized to unit power, 0.5 * Re integral (E x H*) . z dA = 1.
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .project import Project

_DB = 20 / np.log(10)


@dataclass
class Mode:
    neff: complex
    wavelength: float
    x: np.ndarray  # (Nx,) sample coordinates, microns
    y: np.ndarray  # (Ny,)
    dx: np.ndarray  # (Nx,) integration weights (cell widths)
    dy: np.ndarray  # (Ny,)
    E: np.ndarray  # (3, Nx, Ny) complex: Ex, Ey, Ez
    H: np.ndarray  # (3, Nx, Ny) complex: eta0 * (Hx, Hy, Hz)
    eps: np.ndarray  # (Nx, Ny) complex permittivity at the sample points
    # (Nx, Ny) d(omega*eps)/d(omega) at the sample points; None means non-dispersive (= eps)
    eps_group: Optional[np.ndarray] = None
    # group index computed by the backend on its own grid; None falls back to the cell-centre estimate
    ng: Optional[float] = None
    meta: dict = field(default_factory=dict)

    @property
    def k0(self) -> float:
        return 2 * np.pi / self.wavelength

    @property
    def dA(self) -> np.ndarray:
        return np.outer(self.dx, self.dy)

    def integrate(self, f) -> complex:
        return np.sum(f * self.dA)

    def normalize(self) -> "Mode":
        """Scale to unit power and make the dominant transverse E component real-positive at its peak."""
        t = self.E[0] if np.abs(self.E[0]).max() >= np.abs(self.E[1]).max() else self.E[1]
        peak = t.flat[np.argmax(np.abs(t))]
        scale = np.conj(peak) / abs(peak) / np.sqrt(abs(self.power))
        self.E = self.E * scale
        self.H = self.H * scale
        return self

    @property
    def power(self) -> float:
        Sz = self.E[0] * np.conj(self.H[1]) - self.E[1] * np.conj(self.H[0])
        return 0.5 * np.real(self.integrate(Sz))

    @property
    def loss_db_per_cm(self) -> float:
        return _DB * self.k0 * np.imag(self.neff) * 1e4

    @property
    def te_fraction(self) -> float:
        """Fraction of transverse electric energy in Ex (Lumerical's definition)."""
        ex = self.integrate(np.abs(self.E[0]) ** 2).real
        ey = self.integrate(np.abs(self.E[1]) ** 2).real
        return ex / (ex + ey)

    @property
    def effective_area(self) -> float:
        """(integral |E|^2)^2 / integral |E|^4, in square microns."""
        I = np.sum(np.abs(self.E) ** 2, axis=0)
        return self.integrate(I).real ** 2 / self.integrate(I**2).real

    @property
    def group_index(self) -> float:
        """c / v_g from the energy velocity, including material dispersion.

        n_g = integral(Re[d(omega eps)/d(omega)] |E|^2 + |H|^2) / (4 P). For lossless
        materials this equals d(k0 neff)/d(k0) exactly (Hellmann-Feynman), so it
        accounts for both waveguide and material dispersion from a single solve.
        With absorbing materials it is an approximation.
        """
        if self.ng is not None:
            return self.ng
        eps_g = self.eps if self.eps_group is None else self.eps_group
        U = self.integrate(np.real(eps_g) * np.sum(np.abs(self.E) ** 2, 0) + np.sum(np.abs(self.H) ** 2, 0))
        return np.real(U) / (4 * self.power)

    def __repr__(self):
        return (f"Mode(neff={self.neff.real:.6f}{self.neff.imag:+.2e}j, loss={self.loss_db_per_cm:.3g} dB/cm, "
                f"TE={self.te_fraction:.3f}, Aeff={self.effective_area:.4f} um^2)")


@dataclass
class ModeSet:
    modes: list[Mode]
    project: Project
    backend: str

    def __len__(self):
        return len(self.modes)

    def __getitem__(self, i) -> Mode:
        return self.modes[i]

    def __iter__(self):
        return iter(self.modes)

    @property
    def neff(self) -> np.ndarray:
        return np.array([m.neff for m in self.modes])

    def table(self) -> str:
        rows = [f"{'#':>2}  {'neff':>10}  {'Im(neff)':>10}  {'loss dB/cm':>10}  {'TE frac':>7}  {'ng':>7}  {'Aeff um2':>8}"]
        for i, m in enumerate(self.modes):
            rows.append(f"{i:>2}  {m.neff.real:>10.6f}  {m.neff.imag:>10.2e}  {m.loss_db_per_cm:>10.3g}  "
                        f"{m.te_fraction:>7.3f}  {m.group_index:>7.4f}  {m.effective_area:>8.4f}")
        return "\n".join(rows)
