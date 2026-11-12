"""Mode overlaps, coupling to Gaussian beams, and coupled-waveguide quantities."""
from typing import Literal, Optional

import numpy as np

from .results import Mode


def overlap(a: Mode, b: Mode) -> float:
    """Power overlap of two modes, |<a,b>| |<b,a>| / (<a,a> <b,b>), with <a,b> = 0.5 integral (E_a x H_b*) . z dA.

    Identifies the same mode between solves (1 for identical fields, 0 for orthogonal modes) and
    estimates butt coupling between similar guides. It neglects reflection at the junction and is
    not bounded by 1 when the two fields live in media of different impedance; for coupling from
    a beam or fiber use field_overlap / gaussian_coupling. Fields on different grids are resampled.
    """
    return a.overlap(b)


def field_overlap(a: Mode, b: Mode) -> float:
    """Transverse electric-field overlap |integral E_a . E_b*|^2 / (integral |E_a|^2 integral |E_b|^2), 0 to 1.

    The usual mode-mismatch coupling efficiency between a beam (or fiber mode) and a waveguide mode.
    """
    Eb = b.E
    if b.E.shape != a.E.shape or not (np.allclose(a.x, b.x) and np.allclose(a.y, b.y)):
        Eb, _ = b._resample(a.x, a.y)
    num = abs(a.integrate(a.E[0] * np.conj(Eb[0]) + a.E[1] * np.conj(Eb[1]))) ** 2
    den = (a.integrate(np.abs(a.E[0]) ** 2 + np.abs(a.E[1]) ** 2).real
           * a.integrate(np.abs(Eb[0]) ** 2 + np.abs(Eb[1]) ** 2).real)
    return float(num / den) if den > 0 else 0.0


def gaussian_beam(x, y, waist: float, wavelength: float, center=(0.0, 0.0), n: float = 1.0,
                  polarization: Literal["x", "y"] = "x") -> Mode:
    """Paraxial Gaussian beam at its waist, E ~ exp(-r^2 / w^2), on the grid (x, y), unit power.

    `waist` is the 1/e field radius (mode field diameter / 2), e.g. about 5.2 um for SMF-28 at 1550 nm.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    X, Y = np.meshgrid(x, y, indexing="ij")
    g = np.exp(-((X - center[0]) ** 2 + (Y - center[1]) ** 2) / waist**2).astype(complex)
    E = np.zeros((3, len(x), len(y)), complex)
    H = np.zeros_like(E)
    if polarization == "x":
        E[0], H[1] = g, n * g
    else:
        E[1], H[0] = g, -n * g

    def widths(c):
        if len(c) == 1:
            return np.ones(1)
        edges = np.concatenate([[c[0] - (c[1] - c[0]) / 2], (c[1:] + c[:-1]) / 2, [c[-1] + (c[-1] - c[-2]) / 2]])
        return np.diff(edges)

    m = Mode(neff=complex(n), wavelength=wavelength, x=x, y=y, dx=widths(x), dy=widths(y), E=E, H=H,
             eps=np.full(X.shape, n**2, complex), meta={"source": "gaussian", "waist": waist})
    return m.normalize()


def gaussian_coupling(mode: Mode, waist: float, center=(0.0, 0.0),
                      polarization: Optional[Literal["x", "y"]] = None) -> float:
    """Mode-mismatch coupling efficiency from a Gaussian beam (e.g. a lensed or cleaved fiber) into `mode`.

    Uses the transverse E-field overlap; Fresnel reflection at the facet is not included.
    The overlap is integrated over the mode's domain (where the mode lives); the beam's power is
    counted over the whole plane, so beams larger than the domain are handled correctly.
    polarization defaults to the mode's dominant transverse E component.
    """
    if polarization is None:
        polarization = "x" if mode.te_fraction >= 0.5 else "y"
    X, Y = np.meshgrid(mode.x, mode.y, indexing="ij")
    g = np.exp(-((X - center[0]) ** 2 + (Y - center[1]) ** 2) / waist**2)
    Et = mode.E[0] if polarization == "x" else mode.E[1]
    num = abs(mode.integrate(Et * g)) ** 2
    mode_norm = mode.integrate(np.abs(mode.E[0]) ** 2 + np.abs(mode.E[1]) ** 2).real
    # normalize the beam over the whole plane, so a beam larger than the domain is not overcounted
    return float(num / (mode_norm * np.pi * waist**2 / 2))


def coupling_length(even: Mode, odd: Mode) -> float:
    """Length (um) for full power transfer between two coupled guides, from their supermodes.

    L_c = lambda / (2 |n_even - n_odd|): light launched in one guide moves completely to the other
    after L_c when the guides are identical (otherwise the transfer is partial).
    """
    dn = abs(np.real(even.neff - odd.neff))
    return float("inf") if dn == 0 else even.wavelength / (2 * dn)


def beat_length(a: Mode, b: Mode) -> float:
    """Length (um) over which two modes accumulate a 2 pi phase difference: lambda / |n_a - n_b|."""
    dn = abs(np.real(a.neff - b.neff))
    return float("inf") if dn == 0 else a.wavelength / dn
