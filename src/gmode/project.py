"""Project: everything needed to define and reproduce a mode solve. Serializes to JSON."""
import warnings
from pathlib import Path
from typing import Literal, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .geometry import Structure
from .materials import Material, material

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
    # coordinate stretch s = 1 + (kappa + i*sigma) * (depth/thickness)^order.
    # sigma (absorption): None picks a value for ~1e-6 normal-incidence reflection.
    # kappa (real stretch, damps evanescent tails): None uses kappa = sigma, which
    # keeps spurious PML modes below the local material index.
    pml_sigma: Optional[float] = None
    pml_kappa: Optional[float] = Field(None, ge=0)

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
    # Bends: radius in microns, None for a straight guide. Along bend_radial_axis the radius is
    # r = R + (u - bend_location), so positive R puts the bend center on the -u side and modes
    # shift toward +u. neff is referenced to radius R, i.e. to the coordinate bend_location
    # (default: the domain center); set it to the waveguide's position. Bend radiation leaves
    # through the outer side, so extend the domain there (several microns) and use PML.
    bend_radius: Optional[float] = None
    bend_radial_axis: Literal["x", "y"] = "x"
    bend_location: Optional[float] = None

    @model_validator(mode="after")
    def _check_bend(self):
        if self.bend_radius is not None and self.bend_radius == 0:
            raise ValueError("bend_radius must be nonzero (None for a straight guide)")
        return self


class FiberSettings(BaseModel):
    """A Gaussian fiber beam to report coupling against (mode-mismatch overlap at the facet)."""

    # mode field diameter in microns (1/e^2 intensity), e.g. 10.4 for SMF-28 at 1550 nm,
    # 2.5 for a lensed fiber; None turns the report off
    mfd: Optional[float] = Field(None, gt=0)
    center: tuple[float, float] = (0.0, 0.0)


class SweepSettings(BaseModel):
    """What the GUI's sweep panel runs; scripts call gmode.sweep() directly."""

    parameter: str = "wavelength"
    start: float = 1.5
    stop: float = 1.6
    steps: int = Field(11, ge=2)
    extra_modes: int = Field(2, ge=0)
    keep_fields: bool = True

    @property
    def values(self):
        return np.linspace(self.start, self.stop, self.steps)


class Project(BaseModel):
    # re-validate on attribute assignment, so p.materials = {"core": "Si"} resolves library names
    model_config = ConfigDict(validate_assignment=True)

    schema_version: int = SCHEMA_VERSION
    name: str = "untitled"
    description: str = ""
    wavelength: float = Field(1.55, gt=0)
    materials: dict[str, Material]
    background: str
    # later structures are drawn on top of earlier ones
    structures: list[Structure] = []
    domain: Domain = Domain()
    mesh: Mesh = Mesh()
    boundaries: Boundaries = Boundaries()
    solver: SolverSettings = SolverSettings()
    sweep: SweepSettings = SweepSettings()
    fiber: FiberSettings = FiberSettings()

    @field_validator("materials", mode="before")
    @classmethod
    def _resolve_library_names(cls, v):
        """Allow {"core": "Si"} as shorthand for {"core": gm.material("Si")}."""
        if isinstance(v, dict):
            return {k: (material(m) if isinstance(m, str) else m) for k, m in v.items()}
        return v

    @model_validator(mode="after")
    def _check_bend_symmetry(self):
        s = self.solver
        if s.bend_radius is not None and getattr(self.boundaries, f"{s.bend_radial_axis}_symmetry") != "none":
            raise ValueError(f"a bend breaks the mirror symmetry along {s.bend_radial_axis}; "
                             f"set {s.bend_radial_axis}_symmetry to none")
        return self

    @model_validator(mode="after")
    def _check_materials(self):
        for name in [self.background] + [s.material for s in self.structures]:
            if name not in self.materials:
                raise ValueError(f"unknown material {name!r}")
        return self

    def _used_materials(self) -> list[str]:
        return list(dict.fromkeys([self.background] + [s.material for s in self.structures]))

    def _paint(self, x, y, values: dict) -> np.ndarray:
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        out = np.full(x.shape, values[self.background], dtype=complex)
        for s in self.structures:
            out[s.contains(x, y)] = values[s.material]
        return out

    def owner_at(self, x, y) -> np.ndarray:
        """Index of the topmost structure at each point, or -1 for the background."""
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        owner = np.full(x.shape, -1)
        for i, s in enumerate(self.structures):
            owner[s.contains(x, y)] = i
        return owner

    def region_mask(self, region: str, x, y) -> np.ndarray:
        """Points belonging to `region`: a structure name (where it is the topmost structure)
        or a material name (wherever that material is visible, background included)."""
        owner = self.owner_at(x, y)
        names = [s.name for s in self.structures]
        if region in names:
            if names.count(region) > 1:
                raise ValueError(f"more than one structure is named {region!r}")
            return owner == names.index(region)
        if region in self.materials:
            mats = np.array([s.material for s in self.structures] + [self.background])
            return mats[owner] == region  # owner -1 picks the background (last entry)
        raise ValueError(f"no structure or material named {region!r}")

    def eps_at(self, x, y, wavelength: Optional[float] = None) -> np.ndarray:
        """Relative permittivity sampled at points (no interface averaging)."""
        wl = self.wavelength if wavelength is None else wavelength
        return self._paint(x, y, {k: complex(self.materials[k].eps(wl)) for k in self._used_materials()})

    def group_eps_at(self, x, y, wavelength: Optional[float] = None) -> np.ndarray:
        """d(omega*eps)/d(omega) sampled at points; equals eps_at for non-dispersive materials."""
        wl = self.wavelength if wavelength is None else wavelength
        return self._paint(x, y, {k: complex(self.materials[k].group_eps(wl)) for k in self._used_materials()})

    def range_warnings(self, wavelength: Optional[float] = None) -> list[str]:
        """Materials used outside the wavelength range their model is valid for."""
        wl = self.wavelength if wavelength is None else wavelength
        msgs = []
        for k in self._used_materials():
            m = self.materials[k]
            if not m.in_range(wl):
                lo, hi = m.valid_range()
                msgs.append(f"material {k!r} is only valid for {lo:g}-{hi:g} um; extrapolating to {wl:g} um")
        return msgs

    def solve(self):
        from .solvers import get_solver

        for msg in self.range_warnings():
            warnings.warn(msg, stacklevel=2)
        return get_solver(self.solver.backend).solve(self)

    def save(self, path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path) -> "Project":
        return cls.model_validate_json(Path(path).read_text())
