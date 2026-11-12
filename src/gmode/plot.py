"""Matplotlib helpers for headless use; the GUI has its own field viewer."""
import numpy as np

from .results import Mode

_COMPONENTS = {"Ex": ("E", 0), "Ey": ("E", 1), "Ez": ("E", 2), "Hx": ("H", 0), "Hy": ("H", 1), "Hz": ("H", 2)}


def field(mode: Mode, component: str, part: str = "auto"):
    """Return (data, part) for component Ex..Hz, or "E"/"H" (magnitude).

    part is real, imag, abs, or auto: whichever of real/imag carries the field
    (longitudinal components are 90 degrees out of phase with transverse ones).
    """
    if component in ("E", "H"):
        return np.sqrt(np.sum(np.abs(getattr(mode, component)) ** 2, axis=0)), "abs"
    which, i = _COMPONENTS[component]
    f = getattr(mode, which)[i]
    if part == "auto":
        part = "real" if np.abs(f.real).max() >= np.abs(f.imag).max() else "imag"
    return {"real": np.real, "imag": np.imag, "abs": np.abs}[part](f), part


def plot_mode(mode: Mode, component: str = "E", part: str = "auto", ax=None, outline: bool = True):
    import matplotlib.pyplot as plt

    ax = ax or plt.gca()
    f, part = field(mode, component, part)
    signed = component not in ("E", "H") and part != "abs"
    vmax = np.abs(f).max()
    im = ax.pcolormesh(mode.x, mode.y, f.T, shading="auto", cmap="RdBu_r" if signed else "inferno",
                       vmin=-vmax if signed else 0, vmax=vmax)
    if outline:
        e = np.real(mode.eps)
        if e.max() > e.min():
            ax.contour(mode.x, mode.y, e.T, levels=np.unique(e)[1:] - 1e-9, colors="k", linewidths=0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("x (µm)")
    ax.set_ylabel("y (µm)")
    label = component if component in ("E", "H") else f"{part}({component})"
    ax.set_title(f"{label}   neff = {mode.neff.real:.5f}{mode.neff.imag:+.1e}j", fontsize=9)
    plt.colorbar(im, ax=ax, shrink=0.8)
    return im
