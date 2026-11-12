# Scripting GMode

Everything the desktop app does is available from Python, and the app saves the same
project files that scripts use. Lengths are in microns, the time dependence is exp(-iωt)
(so loss shows up as Im(n_eff) > 0), modes propagate along +z, and the cross-section is
the x-y plane with y vertical.

```python
import numpy as np
import gmode as gm
```

## 1. Describe the problem

A `Project` holds everything needed to reproduce a solve.

```python
p = gm.Project(
    name="si_strip",
    wavelength=1.55,
    materials={"Si": "Si", "SiO2": "SiO2"},        # library names, or material objects
    background="SiO2",
    structures=[gm.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
    domain=gm.Domain(center=(0, 0), size=(3.0, 2.0)),
    mesh=gm.Mesh(dx=0.02, dy=0.02),
    boundaries=gm.Boundaries(x_symmetry="pec", y_symmetry="pmc"),   # TE-like modes, quarter domain
    solver=gm.SolverSettings(num_modes=2),
)
p.save("si_strip.gmode")            # JSON; open it in the app, or gm.Project.load(...)
```

**Structures** are `Rectangle(center, size)`, `Circle(center, radius)` and
`Polygon(vertices)`; `Polygon.trapezoid(material, center, top_width, height, sidewall_angle)`
builds an etched ridge with sloped walls. Later structures are drawn on top of earlier ones.
Let substrates and slabs extend past the domain edge if they continue on the chip.

**Boundaries.** The outer walls are `pec` (default), `pmc`, `periodic` or `pml`. PML layers
are added *outside* the domain (`pml_layers`, default 20 cells). Use PML wherever a mode can
leak (substrate leakage, bends, lateral leakage in ribs). A symmetry plane through the domain
center halves the work and selects a mode family: for TE-like (Ex-dominant) modes use
`x_symmetry="pec"`, `y_symmetry="pmc"`; for TM-like use the opposite.

**Mesh.** `subpixel` (default 4) averages the permittivity at interfaces, which makes results
converge smoothly as the mesh is refined. Check convergence with a sweep over `mesh.step`
(section 5).

## 2. Solve and read the results

```python
modes = p.solve()                 # a ModeSet
print(modes.table())
m = modes[0]
m.neff, m.loss_db_per_cm, m.group_index, m.te_fraction, m.effective_area
m.E, m.H                          # (3, Nx, Ny) arrays on the grid m.x, m.y; H is scaled by eta0
```

Modes are normalized to unit power and sorted by Re(n_eff). They are searched around
`solver.target_neff` (default: the largest index present). Set it near the n_eff you expect
when the modes you want are not the highest-index ones.

The **group index** includes material dispersion and comes from each solve directly: it is the
exact derivative d(k0 n_eff)/d(k0) of the discretized problem, so it equals what you would get
from finite differences over wavelength.

```python
from gmode.plot import plot_mode
plot_mode(m, "Ex")                # matplotlib, for scripts and notebooks
```

## 3. Materials

```python
gm.material_library()                     # every built-in, with source and valid range
gm.material("Si").index(1.31)             # complex index at a wavelength
gm.material("AlGaAs", x=0.3)              # composition-dependent
gm.ConstantMaterial(n=1.6, k=1e-4)
gm.SellmeierMaterial(terms=[(B1, C1), (B2, C2)])          # C in um^2
gm.LorentzDrudeMaterial(eps_inf=1, poles=[gm.LorentzPole(strength=..., resonance=..., damping=...)])
gm.TabulatedMaterial.from_file("gold.csv", wavelength_unit="nm")   # wavelength, n[, k]
```

Solving outside a model's valid range gives a warning. Projects store materials by value, so a
saved project does not change if the library does.

## 4. Save results

```python
modes.save("modes.npz")              # all fields and the project; gm.ModeSet.load(...) reads it back
modes.to_csv("modes.csv")            # one row per mode
```

The `.npz` files are plain numpy archives (`np.load` works on them).

## 5. Sweeps

```python
r = gm.sweep(p, "structures.core.size.0", np.linspace(0.4, 0.9, 26))
r.neff[:, 1]          # tracked mode 1 at every width; nan after it is cut off
r.te_fraction         # (steps, tracks)
r.to_csv("width.csv"); r.save("width.npz")

r = gm.sweep(p, "wavelength", np.linspace(1.5, 1.6, 11))
r.group_index[:, 0]; r.dispersion()[:, 0]      # D in ps/(nm km)
```

The parameter is a dotted path to any number in the project (`wavelength`,
`structures.<name>.size.0`, `structures.<name>.center.1`, `materials.<name>.n`,
`domain.size.0`, `solver.bend_radius`, `mesh.step` for dx and dy together) or a function
`(project, value) -> project`. Modes are matched between steps by field overlap, so they keep
their identity through crossings. Steps run in parallel processes (`workers=`, default one per
core); `keep_fields=True` keeps every step's fields for `r.mode(step, track)`.

A convergence check is one line:

```python
r = gm.sweep(p, "mesh.step", [0.04, 0.02, 0.01, 0.005])
```

## 6. Bends

```python
p.solver.bend_radius = 2.0       # microns
p.solver.bend_location = 0.0     # where r = R (the waveguide); default the domain center
p.domain = gm.Domain(center=(1.0, 0), size=(4.0, 2.0))   # extra room on the outside
p.boundaries = gm.Boundaries(x_min="pml", x_max="pml", y_min="pml", y_max="pml")
m = p.solve()[0]
m.bend_loss_db_per_90deg
```

Positive R bends around a center on the -x side, so modes shift toward +x and radiate there:
give the domain several microns on that side. Without an explicit target, a bend solve first
finds the straight guide's n_eff and searches near it. Strongly damped radiation states can
appear in the list too; the bend mode is the low-loss one.

## 7. Coupling and confinement

```python
modes.power_fraction(0, "core")          # share of the power in a structure or material
modes.confinement(0, "core")             # Gamma for gain/absorption (modal gain = Gamma * g)
gm.gaussian_coupling(m, waist=5.2)       # into SMF-28 (waist = MFD/2): mode mismatch only
gm.overlap(a, b)                         # power overlap of two modes
gm.coupling_length(even, odd)            # directional coupler from its two supermodes
```

## 8. Examples

```python
gm.examples.catalog()          # name -> title
p = gm.examples.load("curved_slab")
print(p.description)           # what it shows and the reference it should match
```

`python -m gmode.examples ./examples` writes all of them as project files.

## 9. The MPB backend

`p.solver.backend = "mpb"` solves with MIT Photonic Bands, for cross-checks. It needs the
`meep` package (not on PyPI), so install GMode into an environment that has it. MPB is
periodic and lossless: boundaries and symmetries are ignored, and lossy materials and bends are
rejected.

## Troubleshooting

* **Modes with huge loss or n_eff above the core index** are PML or radiation states. Make sure
  structures that should continue (substrates, slabs) extend into the PML, set `target_neff`
  near the mode you want, and for bends extend the domain on the outside.
* **A mode near cutoff changes with domain size**: it is barely guided; enlarge the domain or
  use PML.
* **Slow solves**: use symmetry where the structure allows it, coarsen the mesh outside the
  core region of interest, or ask for fewer modes (each extra mode costs Arnoldi iterations,
  most of all in the radiation continuum).
