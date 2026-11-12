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
    materials={"Si": "Si", "SiO2": "SiO2"},  # built-in dispersive models; or gm.ConstantMaterial(n=...)
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

## Materials

| Model | Use |
|---|---|
| `ConstantMaterial(n, k)` | Non-dispersive, optionally absorbing |
| `SellmeierMaterial(terms=[(B, C), ...])` | Lossless dielectrics; C in um^2 |
| `LorentzDrudeMaterial(poles=[...])` | Metals and absorbing resonances; energies in eV |
| `AlGaAsMaterial(x)` | Al(x)Ga(1-x)As below the gap (Afromowitz model) |
| `TabulatedMaterial.from_file(path)` | Measured wavelength, n, k (e.g. refractiveindex.info CSV) |

Built-ins, via `gm.material(name)` or a name string in `Project.materials`:

| Name | Source | Range (um) |
|---|---|---|
| Si | Li (1980), 293 K | 1.2 to 14 |
| SiO2 | Malitson (1965) | 0.21 to 6.7 |
| Si3N4 | Luke et al. (2015) | 0.31 to 5.5 |
| LiNbO3_o, LiNbO3_e | Zelmon et al. (1997), as isotropic o/e materials | 0.4 to 5 |
| GaAs | Skauli et al. (2003) | 0.97 to 17 |
| AlAs | Fern and Onton (1971) | 0.56 to 2.2 |
| AlGaAs | Afromowitz (1974); `gm.material("AlGaAs", x=0.3)` | about 1.1x the gap wavelength to 3 |
| AlOx | Constant n = 1.60 (approximate, process-dependent) | |
| InP | Pettit and Turner (1965) | 0.95 to 10 |
| Au, Ag, Al | Rakic et al. (1998), Lorentz-Drude | 0.25 to 6.2 (Au), 12.4 (Ag, Al) |
| Air | n = 1 | |

Solving outside a model's range warns. The group index includes material dispersion. The FDE
backend computes it from the energy on the Yee grid, which equals d(k0 neff)/d(k0) of the
discretized problem, so one solve gives the same n_g as finite differences over wavelength.

Conventions: propagation along +z, with x horizontal and y vertical in the cross-section.
Lengths are in microns. Time dependence is exp(-iωt), so loss appears as Im(neff) > 0.

## Roadmap

| | Milestone | Status |
|---|---|---|
| M0 | Package scaffolding, tests | done |
| M1 | Data model and FDE solver with PML, validated against analytic results and MPB | done |
| M2 | Dispersive material library, group index from dispersion | done |
| M3 | PySide6 GUI: geometry editor, solve, mode table, field viewer, project files | |
| M4 | Parameter and wavelength sweeps with mode tracking | |
| M5 | Bend modes, overlaps and coupling, confinement factors | |
| M6 | Data export, scripting docs, app packaging, CI on Windows/Linux/macOS | |

The original tkinter + MPB prototype is in `legacy/`.
