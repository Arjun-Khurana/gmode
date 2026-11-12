"""Optical material models.

Wavelengths are vacuum wavelengths in microns. The time dependence is exp(-i*omega*t),
so absorbing materials have n + i*k with k > 0 and Im(eps) > 0.

Every model exposes eps(wavelength) and group_eps(wavelength) = d(omega*eps)/d(omega),
the permittivity that enters the electromagnetic energy density of a dispersive medium.
Both accept scalars or numpy arrays.
"""
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

import numpy as np
from pydantic import BaseModel, Field, PrivateAttr, model_validator

EV_UM = 1.23984198  # photon energy in eV times vacuum wavelength in microns
_DERIV_STEP = 1e-4  # relative wavelength step for numerical d(eps)/d(lambda)
_ALGAAS_MAX_WAVELENGTH = 3.0  # microns; beyond this the missing phonon terms matter


class _MaterialBase(BaseModel):
    description: str = ""
    reference: str = ""
    # wavelengths (microns) over which the model is valid; None means unrestricted
    wavelength_range: Optional[tuple[float, float]] = None

    def eps(self, wavelength):
        raise NotImplementedError

    def deps_dwavelength(self, wavelength):
        """d(eps)/d(lambda), by central differences unless a model overrides it."""
        h = _DERIV_STEP * np.asarray(wavelength, float)
        return (self.eps(wavelength + h) - self.eps(wavelength - h)) / (2 * h)

    def group_eps(self, wavelength):
        """d(omega*eps)/d(omega) = eps - lambda * d(eps)/d(lambda)."""
        return self.eps(wavelength) - np.asarray(wavelength, float) * self.deps_dwavelength(wavelength)

    def index(self, wavelength):
        """Complex refractive index n + i*k."""
        return np.sqrt(np.asarray(self.eps(wavelength), complex))

    def group_index(self, wavelength):
        """Bulk group index n - lambda * dn/dlambda (real part)."""
        n = self.index(wavelength)
        return np.real(self.group_eps(wavelength) / (2 * n) + n / 2)

    def valid_range(self) -> Optional[tuple[float, float]]:
        return self.wavelength_range

    def in_range(self, wavelength: float) -> bool:
        r = self.valid_range()
        return r is None or r[0] <= wavelength <= r[1]


class ConstantMaterial(_MaterialBase):
    """Non-dispersive material with complex index n + i*k."""

    kind: Literal["constant"] = "constant"
    n: float
    k: float = 0.0

    def eps(self, wavelength):
        return np.zeros_like(np.asarray(wavelength, float), dtype=complex) + complex(self.n, self.k) ** 2

    def deps_dwavelength(self, wavelength):
        return np.zeros_like(np.asarray(wavelength, float))


class SellmeierMaterial(_MaterialBase):
    """Lossless dispersive dielectric:

        n^2 = a + sum_i B_i lambda^2 / (lambda^2 - C_i) + sum_j D_j lambda^p_j

    with lambda in microns and C_i in square microns (resonance wavelength squared).
    The power terms cover formulas that go beyond pure Sellmeier, such as Li's for silicon.
    """

    kind: Literal["sellmeier"] = "sellmeier"
    a: float = 1.0
    terms: list[tuple[float, float]]  # (B_i, C_i)
    power_terms: list[tuple[float, float]] = []  # (D_j, p_j)

    def eps(self, wavelength):
        l2 = np.asarray(wavelength, float) ** 2
        n2 = self.a + sum(b * l2 / (l2 - c) for b, c in self.terms)
        n2 = n2 + sum(d * l2 ** (p / 2) for d, p in self.power_terms)
        return np.asarray(n2, complex)[()]

    def deps_dwavelength(self, wavelength):
        lam = np.asarray(wavelength, float)
        l2 = lam**2
        d = sum(-2 * b * c * lam / (l2 - c) ** 2 for b, c in self.terms)
        d = d + sum(dj * p * lam ** (p - 1) for dj, p in self.power_terms)
        return d + np.zeros_like(lam)


class LorentzPole(BaseModel):
    """One term strength / (resonance^2 - omega^2 - i*damping*omega), all in eV.

    resonance = 0 gives a Drude (free-carrier) term.
    """

    strength: float  # eV^2
    resonance: float = Field(0.0, ge=0)  # eV
    damping: float = Field(0.0, ge=0)  # eV


class LorentzDrudeMaterial(_MaterialBase):
    """eps(omega) = eps_inf + sum_j S_j / (w_j^2 - omega^2 - i*g_j*omega), with photon energies in eV."""

    kind: Literal["lorentz"] = "lorentz"
    eps_inf: float = 1.0
    poles: list[LorentzPole]

    def eps(self, wavelength):
        w = EV_UM / np.asarray(wavelength, float)
        e = self.eps_inf + sum(p.strength / (p.resonance**2 - w**2 - 1j * p.damping * w) for p in self.poles)
        return np.asarray(e, complex)[()]

    def deps_dwavelength(self, wavelength):
        lam = np.asarray(wavelength, float)
        w = EV_UM / lam
        de_dw = sum(p.strength * (2 * w + 1j * p.damping) / (p.resonance**2 - w**2 - 1j * p.damping * w) ** 2
                    for p in self.poles)
        return np.asarray(de_dw * (-w / lam), complex)[()]

    @classmethod
    def rakic(cls, plasma: float, f: list[float], damping: list[float], resonance: list[float], **meta):
        """Build from the Lorentz-Drude parameters of Rakic et al. (1998).

        Index 0 is the Drude term (its resonance is ignored); oscillator j has
        strength f_j * plasma^2.
        """
        poles = [LorentzPole(strength=fj * plasma**2, resonance=(0.0 if j == 0 else wj), damping=gj)
                 for j, (fj, gj, wj) in enumerate(zip(f, damping, resonance))]
        return cls(eps_inf=1.0, poles=poles, **meta)


class AlGaAsMaterial(_MaterialBase):
    """Al(x)Ga(1-x)As below its direct band gap, from Afromowitz's modified single-oscillator model.

    Accurate to about 0.5% from 1 um into the near infrared. The model leaves out
    absorption and lattice (phonon) resonances, so it is not valid at or above the
    gap or in the mid-infrared. For x = 0 or 1 the dedicated GaAs and AlAs fits are
    more accurate.
    M. A. Afromowitz, Solid State Commun. 15, 59 (1974).
    """

    kind: Literal["algaas"] = "algaas"
    x: float = Field(ge=0, le=1)  # aluminium fraction

    def _params(self):
        x = self.x
        e0 = 3.65 + 0.871 * x + 0.179 * x**2  # single-oscillator energy, eV
        ed = 36.1 - 2.45 * x  # dispersion energy, eV
        eg = 1.424 + 1.266 * x + 0.26 * x**2  # direct (Gamma) gap, eV
        return e0, ed, eg

    def gap_wavelength(self) -> float:
        return EV_UM / self._params()[2]

    def valid_range(self):
        if self.wavelength_range is not None:
            return self.wavelength_range
        # stay ~10% in energy below the gap, where the model's log term is accurate
        return (1.1 * self.gap_wavelength(), _ALGAAS_MAX_WAVELENGTH)

    def eps(self, wavelength):
        e0, ed, eg = self._params()
        E = EV_UM / np.asarray(wavelength, float)
        if np.any(E >= eg):
            raise ValueError(f"AlGaAs (x={self.x:g}) model is only valid below the band gap, "
                             f"wavelength > {self.gap_wavelength():.4f} um")
        eta = np.pi * ed / (2 * e0**3 * (e0**2 - eg**2))
        n2 = (1 + ed / e0 + ed / e0**3 * E**2
              + eta / np.pi * E**4 * np.log((2 * e0**2 - eg**2 - E**2) / (eg**2 - E**2)))
        return np.asarray(n2, complex)[()]


class TabulatedMaterial(_MaterialBase):
    """Measured n and k, interpolated with monotone cubic (PCHIP) splines.

    Wavelengths outside the table raise ValueError rather than extrapolating.
    """

    kind: Literal["tabulated"] = "tabulated"
    wavelengths: list[float]  # microns
    n: list[float]
    k: Optional[list[float]] = None

    _splines: Optional[tuple] = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _check(self):
        m = len(self.wavelengths)
        if m < 2:
            raise ValueError("a tabulated material needs at least 2 wavelengths")
        if len(self.n) != m or (self.k is not None and len(self.k) != m):
            raise ValueError("wavelengths, n and k must have the same length")
        order = np.argsort(self.wavelengths)
        wl = np.asarray(self.wavelengths)[order]
        if np.any(np.diff(wl) <= 0):
            raise ValueError("tabulated wavelengths must be distinct")
        self.wavelengths = wl.tolist()
        self.n = np.asarray(self.n)[order].tolist()
        if self.k is not None:
            self.k = np.asarray(self.k)[order].tolist()
        if self.wavelength_range is None:
            self.wavelength_range = (self.wavelengths[0], self.wavelengths[-1])
        self._splines = None
        return self

    def _interp(self):
        if self._splines is None:
            from scipy.interpolate import PchipInterpolator

            wl = np.asarray(self.wavelengths)
            k = np.zeros_like(wl) if self.k is None else np.asarray(self.k)
            self._splines = (PchipInterpolator(wl, self.n, extrapolate=False),
                             PchipInterpolator(wl, k, extrapolate=False))
        return self._splines

    def _nk(self, wavelength, nu=0):
        lam = np.asarray(wavelength, float)
        lo, hi = self.wavelengths[0], self.wavelengths[-1]
        if np.any(lam < lo) or np.any(lam > hi):
            raise ValueError(f"wavelength outside the tabulated range {lo:g}-{hi:g} um")
        sn, sk = self._interp()
        return sn(lam, nu) + 1j * sk(lam, nu)

    def eps(self, wavelength):
        return np.asarray(self._nk(wavelength) ** 2, complex)[()]

    def deps_dwavelength(self, wavelength):
        return np.asarray(2 * self._nk(wavelength) * self._nk(wavelength, 1), complex)[()]

    @classmethod
    def from_file(cls, path, wavelength_unit: Literal["um", "nm"] = "um", **meta) -> "TabulatedMaterial":
        """Read columns wavelength, n[, k] separated by commas, tabs or spaces.

        Lines that are not purely numeric (headers, comments) are skipped, so CSV
        downloads from refractiveindex.info load directly.
        """
        rows = []
        for line in Path(path).read_text().splitlines():
            parts = line.replace(",", " ").replace(";", " ").split()
            try:
                rows.append([float(v) for v in parts])
            except ValueError:
                continue
        rows = [r for r in rows if len(r) >= 2]
        if not rows:
            raise ValueError(f"no numeric wavelength, n[, k] rows found in {path}")
        ncol = min(len(r) for r in rows)
        data = np.array([r[:ncol] for r in rows])
        wl = data[:, 0] * (1e-3 if wavelength_unit == "nm" else 1.0)
        k = data[:, 2].tolist() if ncol >= 3 else None
        meta.setdefault("description", Path(path).stem)
        return cls(wavelengths=wl.tolist(), n=data[:, 1].tolist(), k=k, **meta)


Material = Annotated[
    Union[ConstantMaterial, SellmeierMaterial, LorentzDrudeMaterial, AlGaAsMaterial, TabulatedMaterial],
    Field(discriminator="kind"),
]
