"""Saving and loading results.

    ms.save("modes.npz");  ms = gm.ModeSet.load("modes.npz")   # every field, plus the project
    ms.to_csv("modes.csv")                                      # one row per mode
    result.to_csv("sweep.csv");  result.save("sweep.npz")       # tracked sweep quantities

The .npz files are ordinary numpy archives (np.load works on them directly) and embed the
project as JSON, so a results file always records exactly what produced it.
"""
import csv
import json
from pathlib import Path

import numpy as np

MODES_FORMAT = "gmode-modes"
SWEEP_FORMAT = "gmode-sweep"
FORMAT_VERSION = 1


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(f"cannot serialize {type(o).__name__}")


def _fmt(v) -> str:
    """CSV cell: empty for missing values, full precision otherwise."""
    if v is None:
        return ""
    v = float(v)
    return "" if not np.isfinite(v) else repr(v)


# ---- mode sets ----------------------------------------------------------------------------
def save_modes(modes, path) -> Path:
    path = Path(path)
    arrays = {
        "format": np.array(MODES_FORMAT), "version": np.array(FORMAT_VERSION),
        "project": np.array(modes.project.model_dump_json()), "backend": np.array(modes.backend),
        "count": np.array(len(modes)),
    }
    for i, m in enumerate(modes):
        p = f"mode{i}_"
        arrays.update({
            p + "neff": np.array(m.neff, complex), p + "wavelength": np.array(m.wavelength),
            p + "x": m.x, p + "y": m.y, p + "dx": m.dx, p + "dy": m.dy,
            p + "E": m.E, p + "H": m.H, p + "eps": m.eps,
            p + "ng": np.array(np.nan if m.ng is None else m.ng),
            p + "meta": np.array(json.dumps(m.meta, default=_json_default)),
        })
        if m.eps_group is not None:
            arrays[p + "eps_group"] = m.eps_group
    np.savez_compressed(path, **arrays)
    return path if path.suffix == ".npz" else path.with_suffix(path.suffix + ".npz")


def load_modes(path):
    from .project import Project
    from .results import Mode, ModeSet

    with np.load(path, allow_pickle=False) as z:
        if str(z["format"]) != MODES_FORMAT:
            raise ValueError(f"{path} is not a GMode mode file")
        modes = []
        for i in range(int(z["count"])):
            p = f"mode{i}_"
            ng = float(z[p + "ng"])
            modes.append(Mode(
                neff=complex(z[p + "neff"]), wavelength=float(z[p + "wavelength"]),
                x=z[p + "x"], y=z[p + "y"], dx=z[p + "dx"], dy=z[p + "dy"],
                E=z[p + "E"], H=z[p + "H"], eps=z[p + "eps"],
                eps_group=z[p + "eps_group"] if p + "eps_group" in z else None,
                ng=None if np.isnan(ng) else ng, meta=json.loads(str(z[p + "meta"])),
            ))
        return ModeSet(modes, Project.model_validate_json(str(z["project"])), str(z["backend"]))


def modes_to_csv(modes, path) -> Path:
    path = Path(path)
    bend = any(m.bend_radius is not None for m in modes)
    fiber = modes.project.fiber.mfd
    cols = ["mode", "wavelength_um", "neff_real", "neff_imag", "loss_db_per_cm", "group_index",
            "te_fraction", "effective_area_um2"]
    if bend:
        cols.append("bend_loss_db_per_90deg")
    if fiber:
        cols.append(f"fiber_coupling_mfd_{fiber:g}um")
    from .analysis import gaussian_coupling

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, m in enumerate(modes):
            row = [i, _fmt(m.wavelength), _fmt(m.neff.real), _fmt(m.neff.imag), _fmt(m.loss_db_per_cm),
                   _fmt(m.group_index), _fmt(m.te_fraction), _fmt(m.effective_area)]
            if bend:
                row.append(_fmt(m.bend_loss_db_per_90deg))
            if fiber:
                row.append(_fmt(gaussian_coupling(m, fiber / 2, modes.project.fiber.center)))
            w.writerow(row)
    return path


# ---- sweeps -------------------------------------------------------------------------------
_SWEEP_ARRAYS = ("values", "neff", "group_index", "loss_db_per_cm", "te_fraction", "effective_area", "overlap",
                 "wavelengths")


def save_sweep(result, path) -> Path:
    path = Path(path)
    assign = np.array([[-1 if j is None else j for j in a] for a in result.assignments], dtype=int) \
        if result.assignments else np.zeros((0, result.n_tracks), int)
    np.savez_compressed(path, format=np.array(SWEEP_FORMAT), version=np.array(FORMAT_VERSION),
                        parameter=np.array(result.parameter), assignments=assign,
                        **{k: getattr(result, k) for k in _SWEEP_ARRAYS})
    return path if path.suffix == ".npz" else path.with_suffix(path.suffix + ".npz")


def load_sweep(path):
    from .sweep import SweepResult

    with np.load(path, allow_pickle=False) as z:
        if str(z["format"]) != SWEEP_FORMAT:
            raise ValueError(f"{path} is not a GMode sweep file")
        assignments = [[None if j < 0 else int(j) for j in row] for row in z["assignments"]]
        return SweepResult(parameter=str(z["parameter"]), assignments=assignments,
                           **{k: z[k] for k in _SWEEP_ARRAYS})


def sweep_to_csv(result, path) -> Path:
    """Long format: one row per (step, track); empty cells where a track has no mode."""
    path = Path(path)
    D = None
    if result.parameter == "wavelength" and len(result.values) >= 3:
        D = result.dispersion()
    cols = [result.parameter, "wavelength_um", "track", "neff_real", "neff_imag", "group_index", "loss_db_per_cm",
            "te_fraction", "effective_area_um2", "overlap_with_previous"]
    if D is not None:
        cols.append("dispersion_ps_per_nm_km")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for k, v in enumerate(result.values):
            for t in range(result.n_tracks):
                n = result.neff[k, t]
                row = [_fmt(v), _fmt(result.wavelengths[k]), t, _fmt(n.real), _fmt(n.imag),
                       _fmt(result.group_index[k, t]), _fmt(result.loss_db_per_cm[k, t]),
                       _fmt(result.te_fraction[k, t]), _fmt(result.effective_area[k, t]), _fmt(result.overlap[k, t])]
                if D is not None:
                    row.append(_fmt(D[k, t]))
                w.writerow(row)
    return path
