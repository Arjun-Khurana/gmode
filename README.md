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

## Desktop app

```sh
uv sync --extra gui
uv run gmode-gui            # or: uv run python -m gmode.gui [project.gmode]
```

Draw rectangles, circles, sloped ridges and polygons (drag to move, handles to resize, with
snapping), pick materials from the library or import n,k data, set the domain, mesh,
boundaries and symmetry in the properties panel, then press F5. Solves run in a separate process,
so they can be cancelled. Results show the mode list, n_eff, n_g, loss, A_eff and TE fraction,
and every field component (Re, Im, |.|, dB). Projects save as JSON (`.gmode`), with full undo/redo.

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

## Sweeps

```python
import numpy as np

# width sweep: modes are tracked by field overlap, so they keep their identity through crossings
r = gm.sweep(p, "structures.core.size.0", np.linspace(0.4, 0.9, 26))
r.neff[:, 1]           # mode 1 at every width (nan once it is cut off)
r.te_fraction          # (steps, modes): polarization along each track
print(r.table())

# wavelength sweep: n_g per step (exact, with material dispersion) and the dispersion D
r = gm.sweep(p, "wavelength", np.linspace(1.5, 1.6, 11))
r.dispersion()         # ps/(nm km), from d n_g / d lambda
```

Any number in the project can be swept by its path: `wavelength`, `structures.<name>.size.0`
(width), `structures.<name>.center.1`, `materials.<name>.n`, `domain.size.0`, or `mesh.step`
(dx and dy, for convergence checks). A function `(project, value) -> project` works too.
Steps run in parallel worker processes (one per core by default). Each step solves a couple of extra
modes, so a tracked mode can't drop out of the search window when another mode crosses it. In the
desktop app, the Sweep view (F6) plots any tracked quantity, and clicking a point opens that step's
fields.

## Bends, coupling and confinement

```python
# bend: radius measured at the waveguide (x = 0); extend the domain on the outside and use PML
p.solver.bend_radius, p.solver.bend_location = 2.0, 0.0
m = p.solve()[0]
m.bend_loss_db_per_90deg

ms.confinement(0, "core")        # Gamma for gain/absorption (Visser et al.), by structure or material
ms.power_fraction(0, "core")     # share of the guided power
gm.gaussian_coupling(m, 5.2)     # into SMF-28 (waist = MFD/2), mode mismatch only
gm.overlap(a, b)                 # power overlap of two modes, e.g. butt coupling
gm.coupling_length(even, odd)    # directional coupler, from its supermodes
```

Bends use the conformal transformation (scaled eps and mu on the Yee grid) and are checked
against the exact complex-order Bessel solution of a curved slab: n_eff to 2e-4, loss to 3%.

## Examples

`gm.examples.load(name)` returns a ready project; the desktop app lists them under
File > Open Example, and `python -m gmode.examples ./examples` writes them all as `.gmode` files.
Most are validation cases whose description states the independent reference:
the Si strip (published compact model), a Si wire (MPB), an Si slab (exact), a leaky SiN slab
over silicon (exact, 271 dB/cm), a curved slab (exact Bessel solution), a width sweep through a
mode crossing, a wavelength sweep for n_g and dispersion, a strip bend, a directional coupler,
a fiber edge coupler (inverse taper tip), a rib, a SiN strip, a GaAs/AlGaAs ridge and a
thin-film LiNbO3 ridge.

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
| M3 | PySide6 GUI: geometry editor, solve, mode table, field viewer, project files | done |
| M4 | Parameter and wavelength sweeps with mode tracking | done |
| M5 | Bend modes, overlaps and coupling, confinement factors | done |
| M6 | Data export, scripting docs, app packaging, CI on Windows/Linux/macOS | |

Later: importer for the refractiveindex.info database (convert its formula and n,k entries to GMode
materials, stored by value in the project), Gehrsitz AlGaAs model, anisotropic materials.

The original tkinter + MPB prototype is in `legacy/`.
