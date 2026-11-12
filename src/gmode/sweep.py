"""Parameter and wavelength sweeps with mode tracking.

    result = gm.sweep(project, "structures.core.size.0", np.linspace(0.4, 0.9, 26))
    result.neff[:, 0]            # tracked mode 0 at every step
    result.dispersion()          # for wavelength sweeps, D in ps/(nm km)

Modes are matched between consecutive steps by the power overlap of their
fields (an optimal assignment), so a mode keeps its identity through crossings
instead of being re-sorted by n_eff at every step.
"""
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence, Union

import numpy as np
from scipy.optimize import linear_sum_assignment

from .project import Project
from .results import Mode, ModeSet

C0 = 299792458.0  # m/s
Setter = Callable[[Project, float], Project]


# ---- parameter paths ----------------------------------------------------------------------
def _resolve(container, key: str):
    """One path step: dict key, list index, or (for lists of named items) the item with that name."""
    if isinstance(container, dict):
        if key not in container:
            raise KeyError(key)
        return key
    if isinstance(container, (list, tuple)):
        if key.lstrip("-").isdigit():
            i = int(key)
            container[i]  # IndexError if out of range
            return i
        matches = [i for i, it in enumerate(container) if isinstance(it, dict) and it.get("name") == key]
        if len(matches) != 1:
            raise KeyError(f"{'no' if not matches else 'more than one'} item named {key!r}")
        return matches[0]
    raise KeyError(key)


_ALIASES = {"mesh.step": ("mesh.dx", "mesh.dy")}


def get_parameter(project: Project, path: str) -> float:
    """Current value at a dotted path, e.g. "structures.core.size.0" or "materials.Si.n"."""
    path = _ALIASES.get(path, (path,))[0]
    node = project.model_dump()
    for key in path.split("."):
        node = node[_resolve(node, key)]
    if not isinstance(node, (int, float)):
        raise TypeError(f"{path!r} is not a number")
    return float(node)


def set_parameter(project: Project, path: str, value: float) -> Project:
    """A validated copy of `project` with the number at `path` set to `value`.

    Paths are dotted: dict keys, list indices, or structure names, e.g.
    "wavelength", "structures.core.size.0" (width), "structures.1.center.1",
    "materials.Si.n", "domain.size.0", and "mesh.step" (sets dx and dy).
    """
    data = project.model_dump(mode="json")  # tuples become lists, so every level is assignable
    for p in _ALIASES.get(path, (path,)):
        keys = p.split(".")
        node = data
        try:
            for key in keys[:-1]:
                node = node[_resolve(node, key)]
            last = _resolve(node, keys[-1])
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"bad parameter path {path!r}: {e}") from None
        cur = node[last]
        if isinstance(cur, bool) or not isinstance(cur, (int, float)):
            raise ValueError(f"{path!r} is not a number")
        node[last] = int(round(value)) if isinstance(cur, int) else float(value)
    return Project.model_validate(data)


def parameter_label(path: str) -> str:
    """Readable name for a path, e.g. "core width (µm)"."""
    parts = path.split(".")
    named = {"size.0": "width", "size.1": "height", "center.0": "x", "center.1": "y", "radius": "radius"}
    if path == "wavelength":
        return "wavelength (µm)"
    if path == "mesh.step":
        return "mesh step (µm)"
    if parts[0] == "structures" and len(parts) >= 3:
        what = named.get(".".join(parts[2:]), ".".join(parts[2:]))
        return f"{parts[1]} {what} (µm)"
    if parts[0] == "materials" and len(parts) == 3:
        return f"{parts[1]} {parts[2]}"
    return path


# ---- tracking -----------------------------------------------------------------------------
class ModeTracker:
    """Follows modes through consecutive steps by field overlap.

    The first step's modes start the tracks. At each later step every track is
    matched to one candidate mode, maximizing the total overlap with the track's
    most recent mode; a match below `min_overlap` leaves the track empty for that
    step. A mode that is cut off therefore ends its track rather than continuing
    as a radiation mode. Very coarse steps near cutoff can end a track early.
    """

    def __init__(self, n_tracks: int, min_overlap: float = 0.5):
        self.n_tracks = n_tracks
        self.min_overlap = min_overlap
        self.last: list[Optional[Mode]] = []
        self.assignments: list[list[Optional[int]]] = []  # per step: candidate index per track
        self.overlaps: list[list[float]] = []

    def add(self, modes: Sequence[Mode]) -> list[Optional[int]]:
        if not self.last:
            n = min(self.n_tracks, len(modes))
            self.last = list(modes[:n]) + [None] * (self.n_tracks - n)
            pick = list(range(n)) + [None] * (self.n_tracks - n)
            self.assignments.append(pick)
            self.overlaps.append([1.0] * n + [0.0] * (self.n_tracks - n))
            return pick
        active = [t for t in range(self.n_tracks) if self.last[t] is not None]
        O = np.zeros((len(active), len(modes)))
        for a, t in enumerate(active):
            for j, m in enumerate(modes):
                O[a, j] = self.last[t].overlap(m)
        pick: list[Optional[int]] = [None] * self.n_tracks
        ov = [0.0] * self.n_tracks
        if O.size:
            rows, cols = linear_sum_assignment(-O)
            for a, j in zip(rows, cols):
                t = active[a]
                if O[a, j] >= self.min_overlap:
                    pick[t], ov[t] = int(j), float(O[a, j])
                    self.last[t] = modes[j]
        self.assignments.append(pick)
        self.overlaps.append(ov)
        return pick


# ---- results ------------------------------------------------------------------------------
@dataclass
class SweepResult:
    parameter: str
    values: np.ndarray  # (n_steps,)
    neff: np.ndarray  # (n_steps, n_tracks) complex; nan where a track has no mode
    group_index: np.ndarray  # (n_steps, n_tracks)
    loss_db_per_cm: np.ndarray
    te_fraction: np.ndarray
    effective_area: np.ndarray
    overlap: np.ndarray  # (n_steps, n_tracks) overlap with the previous step's mode
    wavelengths: np.ndarray  # (n_steps,)
    # full results per step when kept (keep_fields=True); modes[step] is a ModeSet of all candidates
    steps: list = field(default_factory=list)
    assignments: list = field(default_factory=list)  # per step: candidate index for each track

    @property
    def n_tracks(self) -> int:
        return self.neff.shape[1]

    @property
    def label(self) -> str:
        return parameter_label(self.parameter)

    def mode(self, step: int, track: int) -> Optional[Mode]:
        """The tracked mode with its fields (requires keep_fields=True)."""
        if not self.steps:
            raise ValueError("fields were not kept; run the sweep with keep_fields=True")
        j = self.assignments[step][track]
        return None if j is None else self.steps[step][j]

    def dispersion(self) -> np.ndarray:
        """Group-velocity dispersion D = (1/c) d n_g / d lambda in ps/(nm km), per step and track.

        Only for wavelength sweeps. n_g already includes material dispersion and is
        exact for each solve, so a single numerical derivative suffices.
        """
        if self.parameter != "wavelength":
            raise ValueError("dispersion needs a wavelength sweep")
        if len(self.values) < 3:
            raise ValueError("dispersion needs at least 3 wavelengths")
        lam = self.values * 1e-6  # m
        dng = np.gradient(self.group_index, lam, axis=0, edge_order=2)  # 1/m
        return dng / C0 * 1e6  # s/m^2 -> ps/(nm km)

    def save(self, path):
        """Write the tracked quantities to a compressed .npz file (fields are not included)."""
        from .io import save_sweep

        return save_sweep(self, path)

    @classmethod
    def load(cls, path) -> "SweepResult":
        from .io import load_sweep

        return load_sweep(path)

    def to_csv(self, path):
        """Long-format CSV: one row per step and track (plus D for wavelength sweeps)."""
        from .io import sweep_to_csv

        return sweep_to_csv(self, path)

    def table(self) -> str:
        head = f"{self.label:>18}" + "".join(f"  {'n_eff ' + str(t):>12}" for t in range(self.n_tracks))
        rows = [head]
        for k, v in enumerate(self.values):
            rows.append(f"{v:>18.6g}" + "".join(
                f"  {self.neff[k, t].real:>12.6f}" if np.isfinite(self.neff[k, t]) else f"  {'-':>12}"
                for t in range(self.n_tracks)))
        return "\n".join(rows)


class SweepCollector:
    """Accumulates step results (in any order), tracks modes in step order and builds a SweepResult."""

    def __init__(self, parameter: str, values, n_tracks: int, keep_fields: bool = False):
        self.parameter = parameter
        self.values = np.asarray(values, float)
        self.n_tracks = n_tracks
        self.keep_fields = keep_fields
        self.tracker = ModeTracker(n_tracks)
        self._pending: dict[int, ModeSet] = {}
        self._next = 0
        n = len(self.values)
        self.neff = np.full((n, n_tracks), np.nan, dtype=complex)
        self.scalars = {k: np.full((n, n_tracks), np.nan) for k in
                        ("group_index", "loss_db_per_cm", "te_fraction", "effective_area", "overlap")}
        self.wavelengths = np.full(n, np.nan)
        self.steps: list[Optional[ModeSet]] = [None] * n
        self.assignments: list = [None] * n

    @property
    def done(self) -> int:
        return self._next

    def add(self, step: int, modes: ModeSet):
        """Record step `step`; tracking advances over every consecutive step now available."""
        self._pending[step] = modes
        while self._next in self._pending:
            k = self._next
            ms = self._pending.pop(k)
            pick = self.tracker.add(list(ms))
            self.assignments[k] = pick
            self.wavelengths[k] = ms.project.wavelength
            for t, j in enumerate(pick):
                if j is None:
                    continue
                m = ms[j]
                self.neff[k, t] = m.neff
                self.scalars["group_index"][k, t] = m.group_index
                self.scalars["loss_db_per_cm"][k, t] = m.loss_db_per_cm
                self.scalars["te_fraction"][k, t] = m.te_fraction
                self.scalars["effective_area"][k, t] = m.effective_area
                self.scalars["overlap"][k, t] = self.tracker.overlaps[k][t]
            if self.keep_fields:
                self.steps[k] = ms
            self._next += 1

    def result(self) -> SweepResult:
        n = self._next
        s = self.scalars
        return SweepResult(
            parameter=self.parameter, values=self.values[:n], neff=self.neff[:n],
            group_index=s["group_index"][:n], loss_db_per_cm=s["loss_db_per_cm"][:n],
            te_fraction=s["te_fraction"][:n], effective_area=s["effective_area"][:n], overlap=s["overlap"][:n],
            wavelengths=self.wavelengths[:n], steps=list(self.steps[:n]) if self.keep_fields else [],
            assignments=list(self.assignments[:n]),
        )


# ---- running ------------------------------------------------------------------------------
def step_projects(project: Project, parameter: Union[str, Setter], values, extra_modes: int = 2) -> list[Project]:
    """One project per sweep value, each solving `extra_modes` more modes than are tracked.

    The extra candidates keep a tracked mode from dropping out of the search
    window when another mode crosses it.
    """
    base = project.model_copy(update={"solver": project.solver.model_copy(
        update={"num_modes": project.solver.num_modes + extra_modes})})
    out = []
    for v in values:
        p = parameter(base, float(v)) if callable(parameter) else set_parameter(base, parameter, float(v))
        out.append(p)
    return out


def _solve_json(payload: str) -> ModeSet:
    return Project.model_validate_json(payload).solve()


def default_workers(n_steps: int) -> int:
    # each solve is single-threaded, so one process per core (leaving one free for the desktop)
    return max(1, min(n_steps, (os.cpu_count() or 2) - 1))


def sweep(project: Project, parameter: Union[str, Setter], values, *, workers: Optional[int] = None,
          extra_modes: int = 2, keep_fields: bool = False,
          progress: Optional[Callable[[int, int], None]] = None) -> SweepResult:
    """Solve `project` at each value of `parameter` and track its first num_modes modes.

    parameter: a dotted path (see set_parameter) or a function (project, value) -> project.
    workers: parallel processes (default: one per core, minus one); 1 solves in this process.
    keep_fields: keep every step's modes with fields (memory grows with steps x modes x grid).
    progress: called as progress(done, total) after each step.
    """
    values = np.asarray(values, float)
    projects = step_projects(project, parameter, values, extra_modes)
    name = parameter if isinstance(parameter, str) else getattr(parameter, "__name__", "parameter")
    col = SweepCollector(name, values, project.solver.num_modes, keep_fields)
    workers = default_workers(len(values)) if workers is None else max(1, workers)
    if workers == 1:
        for k, p in enumerate(projects):
            col.add(k, p.solve())
            if progress:
                progress(k + 1, len(values))
        return col.result()
    import multiprocessing as mp

    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as pool:
        futures = {pool.submit(_solve_json, p.model_dump_json()): k for k, p in enumerate(projects)}
        finished = 0
        for fut in as_completed(futures):
            col.add(futures[fut], fut.result())
            finished += 1
            if progress:
                progress(finished, len(values))
    return col.result()
