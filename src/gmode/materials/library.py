"""Built-in materials from published dispersion fits.

    gm.material("Si")       # a fresh copy, ready to put in Project.materials
    gm.material_library()   # every built-in, keyed by name

Lithium niobate is anisotropic. Until tensor permittivity is supported it is
provided as two isotropic materials: LiNbO3_o (ordinary) and LiNbO3_e (extraordinary).
"""
from typing import Callable

from .models import AlGaAsMaterial, ConstantMaterial, LorentzDrudeMaterial, Material, SellmeierMaterial

_RAKIC = "A. D. Rakic et al., Appl. Opt. 37, 5271 (1998); Lorentz-Drude model"


def _air():
    return ConstantMaterial(n=1.0, description="Air / vacuum")


def _si():
    # Li's 293 K fit: n^2 = eps + A / lambda^2 + B lambda1^2 / (lambda^2 - lambda1^2),
    # rewritten in Sellmeier form using B lambda1^2/(lambda^2 - lambda1^2) = B lambda^2/(lambda^2 - lambda1^2) - B
    eps, A, B, lam1 = 11.6858, 0.939816, 0.00810461, 1.1071
    return SellmeierMaterial(
        a=eps - B, terms=[(B, lam1**2)], power_terms=[(A, -2)],
        description="Crystalline silicon, 293 K",
        reference="H. H. Li, J. Phys. Chem. Ref. Data 9, 561 (1980)",
        wavelength_range=(1.2, 14.0),
    )


def _sio2():
    return SellmeierMaterial(
        terms=[(0.6961663, 0.0684043**2), (0.4079426, 0.1162414**2), (0.8974794, 9.896161**2)],
        description="Fused silica (also the usual model for oxide cladding)",
        reference="I. H. Malitson, J. Opt. Soc. Am. 55, 1205 (1965)",
        wavelength_range=(0.21, 6.7),
    )


def _si3n4():
    return SellmeierMaterial(
        terms=[(3.0249, 0.1353406**2), (40314.0, 1239.842**2)],
        description="Stoichiometric LPCVD silicon nitride",
        reference="K. Luke et al., Opt. Lett. 40, 4823 (2015)",
        wavelength_range=(0.31, 5.504),
    )


def _ln_o():
    return SellmeierMaterial(
        terms=[(2.6734, 0.01764), (1.2290, 0.05914), (12.614, 474.60)],
        description="Congruent lithium niobate, ordinary index (isotropic approximation)",
        reference="D. E. Zelmon et al., J. Opt. Soc. Am. B 14, 3319 (1997)",
        wavelength_range=(0.4, 5.0),
    )


def _ln_e():
    return SellmeierMaterial(
        terms=[(2.9804, 0.02047), (0.5981, 0.0666), (8.9543, 416.08)],
        description="Congruent lithium niobate, extraordinary index (isotropic approximation)",
        reference="D. E. Zelmon et al., J. Opt. Soc. Am. B 14, 3319 (1997)",
        wavelength_range=(0.4, 5.0),
    )


def _gaas():
    return SellmeierMaterial(
        a=5.372514,
        terms=[(5.466742, 0.4431307**2), (0.02429960, 0.8746453**2), (1.957522, 36.9166**2)],
        description="Gallium arsenide, room temperature",
        reference="T. Skauli et al., J. Appl. Phys. 94, 6447 (2003)",
        wavelength_range=(0.97, 17.0),
    )


def _alas():
    return SellmeierMaterial(
        a=2.0792, terms=[(6.0840, 0.2822**2), (1.900, 27.62**2)],
        description="Aluminium arsenide",
        reference="R. E. Fern and A. Onton, J. Appl. Phys. 42, 3499 (1971)",
        wavelength_range=(0.56, 2.2),
    )


def _algaas(x: float = 0.3):
    return AlGaAsMaterial(
        x=x, description=f"Al({x:g})Ga({1 - x:g})As; set x for the aluminium fraction",
        reference="M. A. Afromowitz, Solid State Commun. 15, 59 (1974)",
    )


def _alox():
    return ConstantMaterial(
        n=1.60,
        description="Wet-oxidized AlAs / high-Al AlGaAs (AlOx). Approximate: reported values span "
                    "about 1.55-1.65 depending on Al fraction and oxidation process; override with measured data",
    )


def _inp():
    return SellmeierMaterial(
        a=7.255, terms=[(2.316, 0.6263**2), (2.765, 32.935**2)],
        description="Indium phosphide, room temperature",
        reference="G. D. Pettit and W. J. Turner, J. Appl. Phys. 36, 2081 (1965)",
        wavelength_range=(0.95, 10.0),
    )


def _au():
    return LorentzDrudeMaterial.rakic(
        9.03, f=[0.760, 0.024, 0.010, 0.071, 0.601, 4.384],
        damping=[0.053, 0.241, 0.345, 0.870, 2.494, 2.214],
        resonance=[0.0, 0.415, 0.830, 2.969, 4.304, 13.32],
        description="Gold", reference=_RAKIC, wavelength_range=(0.248, 6.2),
    )


def _ag():
    return LorentzDrudeMaterial.rakic(
        9.01, f=[0.845, 0.065, 0.124, 0.011, 0.840, 5.646],
        damping=[0.048, 3.886, 0.452, 0.065, 0.916, 2.419],
        resonance=[0.0, 0.816, 4.481, 8.185, 9.083, 20.29],
        description="Silver", reference=_RAKIC, wavelength_range=(0.248, 12.4),
    )


def _al():
    return LorentzDrudeMaterial.rakic(
        14.98, f=[0.523, 0.227, 0.050, 0.166, 0.030],
        damping=[0.047, 0.333, 0.312, 1.351, 3.382],
        resonance=[0.0, 0.162, 1.544, 1.808, 3.473],
        description="Aluminium", reference=_RAKIC, wavelength_range=(0.248, 12.4),
    )


_LIBRARY: dict[str, Callable[[], Material]] = {
    "Air": _air,
    "Si": _si,
    "SiO2": _sio2,
    "Si3N4": _si3n4,
    "LiNbO3_o": _ln_o,
    "LiNbO3_e": _ln_e,
    "GaAs": _gaas,
    "AlAs": _alas,
    "AlGaAs": _algaas,
    "AlOx": _alox,
    "InP": _inp,
    "Au": _au,
    "Ag": _ag,
    "Al": _al,
}


def material(name: str, **params) -> Material:
    """A fresh copy of the built-in material `name`.

    Parametrized materials take keyword arguments, e.g. material("AlGaAs", x=0.3).
    """
    if name not in _LIBRARY:
        raise ValueError(f"no built-in material {name!r}; available: {', '.join(_LIBRARY)}")
    return _LIBRARY[name](**params)


def material_library() -> dict[str, Material]:
    """Every built-in material, keyed by name (fresh copies)."""
    return {name: make() for name, make in _LIBRARY.items()}
