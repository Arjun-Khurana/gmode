"""Project: everything needed to define and reproduce a mode solve. Serializes to JSON."""
from pathlib import Path
from typing import Literal, Optional

import numpy as np
from pydantic import BaseModel, Field, model_validator

from .geometry import Structure
from .materials import Material

BoundaryType = Literal["pml", "pec", "pmc", "periodic"]
SymmetryType = Literal["none", "pec", "pmc"]

SCHEMA_VERSION = 1


class Domain(BaseModel):
    """Solver region in the cross-section plane (microns). Propagation is along +z."""

    center: tuple[float, float] = (0.0, 0.0)
    size: tuple[float, float] = (3.0, 2.0)


class Mesh(BaseModel):
    dx: float = Field(0.02, gt=0)
    dy: float = Field(0.02, gt=0)
    # samples per cell edge used to average eps at material interfaces (1 = no averaging)
    subpixel: int = Field(4, ge=1)


class Boundaries(BaseModel):
    """Outer boundaries and mirror symmetries.

    PML layers are added outside the domain, so structures should extend past
    the domain edge wherever they are meant to continue (e.g. substrates).

    Symmetry planes pass through the domain center and only half the domain is
    solved. "pec" forces tangential E to zero on the plane, "pmc" tangential H:
    for a TE-like (Ex-dominant) fundamental mode use x_symmetry="pec",
    y_symmetry="pmc"; for TM-like (Ey-dominant) the opposite.
    """

    x_min: BoundaryType = "pec"
    x_max: BoundaryType = "pec"
    y_min: BoundaryType = "pec"
    y_max: BoundaryType = "pec"
    x_symmetry: SymmetryType = "none"
    y_symmetry: SymmetryType = "none"
    pml_layers: int = Field(20, ge=1)
    pml_order: int = 3
    # peak of the coordinate stretch s = 1 + i*sigma*(depth/thickness)^order;
    # None picks a value for ~1e-6 normal-incidence reflection
    pml_sigma: Optional[float] = None

    @model_validator(mode="after")
    def _check(self):
        for ax in "xy":
            lo, hi, sym = getattr(self, f"{ax}_min"), getattr(self, f"{ax}_max"), getattr(self, f"{ax}_symmetry")
            if (lo == "periodic") != (hi == "periodic"):
                raise ValueError(f"periodic {ax} boundaries must be set on both sides")
            if sym != "none" and lo == "periodic":
                raise ValueError(f"{ax} symmetry cannot be combined with periodic boundaries")
        return self


class SolverSettings(BaseModel):
    backend: Literal["fde", "mpb"] = "fde"
    num_modes: int = Field(4, ge=1)
    # modes are searched around this effective index; None uses the largest index in the domain
    target_neff: Optional[float] = None


class Project(BaseModel):
    schema_version: int = SCHEMA_VERSION
    name: str = "untitled"
    wavelength: float = Field(1.55, gt=0)
    materials: dict[str, Material]
    background: str
    # later structures are drawn on top of earlier ones
    structures: list[Structure] = []
    domain: Domain = Domain()
    mesh: Mesh = Mesh()
    boundaries: Boundaries = Boundaries()
    solver: SolverSettings = SolverSettings()

    @model_validator(mode="after")
    def _check_materials(self):
        for name in [self.background] + [s.material for s in self.structures]:
            if name not in self.materials:
                raise ValueError(f"unknown material {name!r}")
        return self

    def eps_at(self, x, y, wavelength: Optional[float] = None) -> np.ndarray:
        """Relative permittivity sampled at points (no interface averaging)."""
        wl = self.wavelength if wavelength is None else wavelength
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        eps = np.full(x.shape, self.materials[self.background].eps(wl), dtype=complex)
        for s in self.structures:
            eps[s.contains(x, y)] = self.materials[s.material].eps(wl)
        return eps

    def solve(self):
        from .solvers import get_solver

        return get_solver(self.solver.backend).solve(self)

    def save(self, path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path) -> "Project":
        return cls.model_validate_json(Path(path).read_text())
