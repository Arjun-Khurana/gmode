"""Mode solver backends. Each backend turns a Project into a ModeSet."""
from typing import Protocol

from ..project import Project
from ..results import ModeSet


class ModeSolver(Protocol):
    name: str

    def solve(self, project: Project) -> ModeSet: ...


def get_solver(name: str) -> ModeSolver:
    if name == "fde":
        from .fde import FDESolver

        return FDESolver()
    if name == "mpb":
        from .mpb import MPBSolver

        return MPBSolver()
    raise ValueError(f"unknown solver backend {name!r}")


def available_backends() -> list[str]:
    backends = ["fde"]
    try:
        import meep.mpb  # noqa: F401

        backends.append("mpb")
    except ImportError:
        pass
    return backends
