"""Optical materials.

Convention: time dependence exp(-i*omega*t), so absorbing materials have
n + i*k with k > 0 and Im(eps) > 0.
"""
from typing import Literal

from pydantic import BaseModel


class ConstantMaterial(BaseModel):
    """Non-dispersive material with complex index n + i*k."""

    kind: Literal["constant"] = "constant"
    n: float
    k: float = 0.0

    def eps(self, wavelength: float) -> complex:
        return complex(self.n, self.k) ** 2

    @property
    def lossless(self) -> bool:
        return self.k == 0.0


# Becomes a discriminated union on `kind` once dispersive models are added.
Material = ConstantMaterial
