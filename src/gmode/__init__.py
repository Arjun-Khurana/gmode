"""GMode: graphical waveguide mode solver."""
from .analysis import beat_length, coupling_length, field_overlap, gaussian_beam, gaussian_coupling, overlap
from .geometry import Circle, Polygon, Rectangle
from .materials import (
    AlGaAsMaterial, ConstantMaterial, LorentzDrudeMaterial, LorentzPole, Material, SellmeierMaterial, TabulatedMaterial, material,
    material_library,
)
from .project import Boundaries, Domain, FiberSettings, Mesh, Project, SolverSettings, SweepSettings
from .results import Mode, ModeSet
from .solvers import available_backends, get_solver
from .sweep import ModeTracker, SweepResult, get_parameter, set_parameter, sweep
from . import examples  # noqa: E402  (after the names it uses)

__all__ = [
    "AlGaAsMaterial", "Boundaries", "Circle", "ConstantMaterial", "Domain", "LorentzDrudeMaterial", "LorentzPole", "Material", "Mesh",
    "Mode", "ModeSet", "Polygon", "Project", "Rectangle", "SellmeierMaterial", "SolverSettings", "TabulatedMaterial",
    "available_backends", "get_solver", "material", "material_library",
    "ModeTracker", "SweepResult", "SweepSettings", "get_parameter", "set_parameter", "sweep",
    "FiberSettings", "examples", "beat_length", "coupling_length", "field_overlap", "gaussian_beam", "gaussian_coupling", "overlap",
]
