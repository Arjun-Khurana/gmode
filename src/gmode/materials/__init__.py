"""Optical materials: dispersion models and the built-in library."""
from .library import material, material_library
from .models import (
    EV_UM, AlGaAsMaterial, ConstantMaterial, LorentzDrudeMaterial, LorentzPole, Material, SellmeierMaterial, TabulatedMaterial,
)

__all__ = [
    "AlGaAsMaterial", "EV_UM", "ConstantMaterial", "LorentzDrudeMaterial", "LorentzPole", "Material", "SellmeierMaterial",
    "TabulatedMaterial", "material", "material_library",
]
