# GMode

A graphical waveguide mode solver, in the spirit of Lumerical FDE and the Tidy3D mode solver.

- **FDE backend** (default): full-vectorial finite-difference eigenmode solver on a Yee grid, with
  PML, PEC/PMC/periodic boundaries, and mirror symmetries. Supports lossy materials and leaky
  modes, returning a complex effective index.
- **MPB backend** (optional): MIT Photonic Bands, for cross-checking and periodic problems.
  It needs the `meep` package, which is not on PyPI.

## Install

```sh
uv sync                 # core + tests
uv sync --extra gui     # + PySide6 GUI (in progress)
uv run pytest
```

To use the MPB backend, install GMode into an environment that already has meep:

```sh
uv pip install --python /path/to/meep/venv/bin/python -e .
```

## Scripting example

```python
import gmode as gm

p = gm.Project(
    wavelength=1.55,
    materials={"Si": gm.ConstantMaterial(n=3.476), "SiO2": gm.ConstantMaterial(n=1.444)},
    background="SiO2",
    structures=[gm.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
    domain=gm.Domain(size=(3, 2)),
    mesh=gm.Mesh(dx=0.01, dy=0.01),
    # TE-like modes only, solving a quarter of the domain
    boundaries=gm.Boundaries(x_symmetry="pec", y_symmetry="pmc"),
)
modes = p.solve()
print(modes.table())
p.save("si_wire.json")
```

Conventions: propagation along +z, with x horizontal and y vertical in the cross-section.
Lengths are in microns. Time dependence is exp(-iωt), so loss appears as Im(neff) > 0.

## Roadmap

| | Milestone | Status |
|---|---|---|
| M0 | Package scaffolding, tests | done |
| M1 | Data model and FDE solver with PML, validated against analytic results and MPB | done |
| M2 | Dispersive material library, group index from dispersion | |
| M3 | PySide6 GUI: geometry editor, solve, mode table, field viewer, project files | |
| M4 | Parameter and wavelength sweeps with mode tracking | |
| M5 | Bend modes, overlaps and coupling, confinement factors | |
| M6 | Data export, scripting docs, app packaging, CI on Windows/Linux/macOS | |

The original tkinter + MPB prototype is in `legacy/`.
