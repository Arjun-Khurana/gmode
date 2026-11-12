"""Example projects, most of them validation cases with an independent reference.

    gm.examples.load("si_strip")        # a Project
    gm.examples.catalog()               # {name: title}
    python -m gmode.examples ./examples # write every example as a .gmode file

The desktop app lists them under File > Open Example.
"""
import sys
from pathlib import Path
from typing import Callable

from . import geometry as g
from .materials import ConstantMaterial, material
from .project import Boundaries, Domain, FiberSettings, Mesh, Project, SolverSettings, SweepSettings

_PML = dict(x_min="pml", x_max="pml", y_min="pml", y_max="pml")


def si_strip() -> Project:
    return Project(
        name="si_strip",
        description=(
            "500 x 220 nm silicon strip in oxide at 1550 nm, the workhorse SOI waveguide.\n"
            "Reference (Chrostowski & Hochberg, Silicon Photonics Design, compact model): "
            "TE0 neff 2.4449, ng about 4.2. GMode gives neff 2.4500 at this 20 nm mesh and "
            "2.4455 at 10 nm, ng 4.19 including silicon's dispersion."),
        materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
        structures=[g.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
        domain=Domain(size=(3.0, 2.0)), mesh=Mesh(dx=0.02, dy=0.02),
        solver=SolverSettings(num_modes=4),
    )


def si_wire_mpb() -> Project:
    return Project(
        name="si_wire_mpb_reference",
        description=(
            "500 x 160 nm Si wire with constant indices (3.476 / 1.444), solved on a quarter of the "
            "domain using both mirror symmetries (TE-like modes only).\n"
            "Reference (MPB, 160 px/um, 3 x 2 um cell): TE0 neff 2.16479, ng 3.8982."),
        materials={"Si": ConstantMaterial(n=3.476), "SiO2": ConstantMaterial(n=1.444)}, background="SiO2",
        structures=[g.Rectangle(name="core", material="Si", size=(0.5, 0.16))],
        domain=Domain(size=(3.0, 2.0)), mesh=Mesh(dx=0.01, dy=0.01),
        boundaries=Boundaries(x_symmetry="pec", y_symmetry="pmc"),
        solver=SolverSettings(num_modes=2),
    )


def si_slab() -> Project:
    return Project(
        name="si_slab_analytic",
        description=(
            "220 nm silicon film in oxide (3.476 / 1.444), infinite in x via a one-cell periodic domain.\n"
            "Reference (exact slab dispersion relation): TE0 neff 2.84778, TM0 neff 2.05332. "
            "Mode 0 is TE (Ex), mode 1 is TM (Ey)."),
        materials={"Si": ConstantMaterial(n=3.476), "SiO2": ConstantMaterial(n=1.444)}, background="SiO2",
        structures=[g.Rectangle(name="film", material="Si", size=(10, 0.22))],
        domain=Domain(size=(0.005, 3.0)), mesh=Mesh(dx=0.005, dy=0.005),
        boundaries=Boundaries(x_min="periodic", x_max="periodic"),
        solver=SolverSettings(num_modes=2),
    )


def leaky_sin_on_si() -> Project:
    return Project(
        name="leaky_sin_slab",
        description=(
            "400 nm SiN film (n = 2.0) on a 600 nm oxide buffer over a silicon substrate. The mode "
            "leaks through the thin buffer into the substrate, absorbed by the PML below.\n"
            "Reference (transverse-resonance solution with an outgoing substrate wave): "
            "TE0 loss 271.2 dB/cm. GMode: about 271.5 dB/cm, independent of PML thickness."),
        materials={"SiN": ConstantMaterial(n=2.0), "SiO2": ConstantMaterial(n=1.444),
                   "Si": ConstantMaterial(n=3.476)}, background="SiO2",
        structures=[g.Rectangle(name="film", material="SiN", center=(0, 0.2), size=(10, 0.4)),
                    g.Rectangle(name="substrate", material="Si", center=(0, -5.6), size=(10, 10))],
        domain=Domain(center=(0, 0.2), size=(0.005, 3.0)), mesh=Mesh(dx=0.005, dy=0.005),
        boundaries=Boundaries(x_min="periodic", x_max="periodic", y_min="pml"),
        solver=SolverSettings(num_modes=4, target_neff=1.9),
    )


def width_sweep_crossing() -> Project:
    p = si_strip()
    return p.model_copy(update=dict(
        name="width_sweep_mode_crossing",
        description=(
            "Width sweep of the 220 nm silicon strip from 0.40 to 0.95 um, tracking three modes. "
            "TE1 rises through TM0 near w = 0.66 um; mode tracking keeps each identity through the "
            "crossing (see the TE fraction plot), where sorting by neff would swap them.\n"
            "Open the Sweep view and press F6."),
        solver=SolverSettings(num_modes=3),
        sweep=SweepSettings(parameter="structures.core.size.0", start=0.40, stop=0.95, steps=23),
    ))


def strip_dispersion() -> Project:
    p = si_strip()
    return p.model_copy(update=dict(
        name="strip_dispersion",
        description=(
            "Wavelength sweep of the 500 x 220 nm strip, 1.50 to 1.60 um, for group index and "
            "dispersion. ng comes from each solve exactly (it matches finite differences of neff to "
            "about 1e-6); D is about +600 ps/(nm km), anomalous.\n"
            "Open the Sweep view, press F6, then choose n_g or D."),
        boundaries=Boundaries(x_symmetry="pec", y_symmetry="pmc"),
        solver=SolverSettings(num_modes=1),
        sweep=SweepSettings(parameter="wavelength", start=1.50, stop=1.60, steps=11),
    ))


def curved_slab() -> Project:
    return Project(
        name="curved_slab_exact",
        description=(
            "A 400 nm film (n = 2.0 in 1.45) bent with radius 5 um, as a leaky bend mode. The domain "
            "extends 5 um on the outside of the bend so the PML can absorb the radiation.\n"
            "Reference (exact solution with complex-order Bessel and Hankel functions): "
            "E along the bend axis: neff 1.75880 + 1.602e-3i; H along the bend axis: 1.67073 + 1.077e-2i."),
        materials={"core": ConstantMaterial(n=2.0), "clad": ConstantMaterial(n=1.45)}, background="clad",
        structures=[g.Rectangle(name="film", material="core", size=(0.4, 10))],
        domain=Domain(center=(1.75, 0), size=(6.5, 0.005)), mesh=Mesh(dx=0.005, dy=0.005),
        boundaries=Boundaries(x_min="pml", x_max="pml", y_min="periodic", y_max="periodic", pml_layers=60),
        solver=SolverSettings(num_modes=2, bend_radius=5.0, bend_location=0.0, target_neff=1.7),
    )


def strip_bend() -> Project:
    return Project(
        name="si_strip_bend",
        description=(
            "500 x 220 nm silicon strip bent with radius 1.5 um. The mode shifts to the outside of "
            "the bend and radiates; the loss is reported in dB per 90 degrees. The domain is "
            "extended on the outer (+x) side for the radiation.\n"
            "The TE bend mode is the low-loss one; strongly damped radiation states can sort above it "
            "(see the loss column). Try other radii in Solver > Bend radius, or sweep "
            "solver.bend_radius in a script. "
            "For rib bends, set a target n_eff near the straight guide's: the slab's radiation "
            "continuum at large radius otherwise attracts the search."),
        materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
        structures=[g.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
        domain=Domain(center=(0.5, 0), size=(3.0, 2.0)), mesh=Mesh(dx=0.02, dy=0.02),
        boundaries=Boundaries(**_PML),
        solver=SolverSettings(num_modes=2, bend_radius=1.5, bend_location=0.0),
    )


def directional_coupler() -> Project:
    return Project(
        name="directional_coupler",
        description=(
            "Two 500 x 220 nm strips with a 200 nm gap. With the pec plane at x = 0 this solves the "
            "even (symmetric) TE supermode; switch x symmetry to pmc for the odd one. The coupling "
            "length is lambda / (2 (n_even - n_odd)), about 38 um here "
            "(gm.coupling_length(even, odd) in a script). Each supermode splits its power evenly "
            "between the guides: see the confinement bars."),
        materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
        structures=[g.Rectangle(name="left", material="Si", center=(-0.35, 0), size=(0.5, 0.22)),
                    g.Rectangle(name="right", material="Si", center=(0.35, 0), size=(0.5, 0.22))],
        domain=Domain(size=(3.5, 2.0)), mesh=Mesh(dx=0.02, dy=0.02),
        boundaries=Boundaries(x_symmetry="pec", y_symmetry="pmc"),
        solver=SolverSettings(num_modes=1),
    )


def si_rib() -> Project:
    return Project(
        name="si_rib",
        description=(
            "Silicon rib: 500 nm wide, 220 nm tall, on a 90 nm slab, oxide below and above. The slab "
            "extends past the domain edge into the PML, as it would on a chip."),
        materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
        structures=[g.Rectangle(name="slab", material="Si", center=(0, -0.065), size=(10, 0.09)),
                    g.Rectangle(name="rib", material="Si", size=(0.5, 0.22))],
        domain=Domain(size=(4.0, 2.0)), mesh=Mesh(dx=0.02, dy=0.02),
        boundaries=Boundaries(x_min="pml", x_max="pml", y_min="pml", y_max="pml"),
        solver=SolverSettings(num_modes=2),
    )


def sin_strip() -> Project:
    return Project(
        name="sin_strip",
        description="1.0 x 0.4 um stoichiometric silicon nitride strip (Luke et al. dispersion) in oxide.",
        materials={"Si3N4": "Si3N4", "SiO2": "SiO2"}, background="SiO2",
        structures=[g.Rectangle(name="core", material="Si3N4", size=(1.0, 0.4))],
        domain=Domain(size=(4.0, 3.0)), mesh=Mesh(dx=0.02, dy=0.02),
        boundaries=Boundaries(x_symmetry="pec"),
        solver=SolverSettings(num_modes=2),
    )


def algaas_ridge() -> Project:
    return Project(
        name="gaas_algaas_ridge",
        description=(
            "Deep-etched GaAs/AlGaAs ridge in air: a 600 nm GaAs core between Al0.4GaAs claddings "
            "(1.5 um below, 300 nm above), 1.2 um wide, on an Al0.4GaAs substrate that continues into "
            "the PML. Shows the composition-dependent AlGaAs material (set x in its properties). "
            "With x = 0.3 and a 400 nm core the mode drops below the cladding index and leaks into "
            "the substrate."),
        materials={"GaAs": "GaAs", "AlGaAs": material("AlGaAs", x=0.4), "air": "Air"}, background="air",
        structures=[g.Rectangle(name="substrate", material="AlGaAs", center=(0, -2.5), size=(10, 2.0)),
                    g.Rectangle(name="lower", material="AlGaAs", center=(0, -0.75), size=(1.2, 1.5)),
                    g.Rectangle(name="core", material="GaAs", center=(0, 0.3), size=(1.2, 0.6)),
                    g.Rectangle(name="upper", material="AlGaAs", center=(0, 0.75), size=(1.2, 0.3))],
        domain=Domain(center=(0, -0.4), size=(4.0, 3.6)), mesh=Mesh(dx=0.02, dy=0.02),
        boundaries=Boundaries(**_PML, x_symmetry="pec"),
        solver=SolverSettings(num_modes=2),
    )


def tfln_ridge() -> Project:
    return Project(
        name="thin_film_ln_ridge",
        description=(
            "X-cut thin-film lithium niobate ridge: 1.2 um top width, sidewalls 30 degrees from "
            "vertical, 300 nm etch into a 600 nm film, on "
            "oxide, air above. The TE mode sees the extraordinary index, approximated here by an "
            "isotropic LiNbO3_e material until anisotropy is supported."),
        materials={"LN": "LiNbO3_e", "SiO2": "SiO2", "air": "Air"}, background="air",
        structures=[g.Rectangle(name="box", material="SiO2", center=(0, -1.5), size=(10, 3.0)),
                    g.Rectangle(name="film", material="LN", center=(0, 0.15), size=(10, 0.3)),
                    g.Polygon.trapezoid("LN", (0, 0.45), 1.2, 0.3, 30.0, name="ridge")],
        domain=Domain(center=(0, 0.3), size=(5.0, 3.0)), mesh=Mesh(dx=0.025, dy=0.02),
        boundaries=Boundaries(**_PML, x_symmetry="pec"),
        solver=SolverSettings(num_modes=2),
    )


def inverse_taper_tip() -> Project:
    return Project(
        name="edge_coupler_tip",
        description=(
            "Silicon inverse-taper tip for fiber edge coupling: 180 x 220 nm, so the mode spreads "
            "into the oxide (A_eff about 2.5 um^2) to match a fiber. The readout shows the coupling "
            "to the fiber set under Fiber coupling (here a lensed fiber, MFD 2.5 um): about -0.5 dB. "
            "Try MFD 10.4 um (SMF-28, about -5 dB), or narrow the tip to 150 nm, where the mode "
            "grows further and the best match moves to MFD about 5 um. Mode-mismatch loss only "
            "(no facet reflection)."),
        materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
        structures=[g.Rectangle(name="tip", material="Si", size=(0.18, 0.22))],
        domain=Domain(size=(10.0, 10.0)), mesh=Mesh(dx=0.02, dy=0.02),
        boundaries=Boundaries(x_symmetry="pec", y_symmetry="pmc"),
        solver=SolverSettings(num_modes=1),
        fiber=FiberSettings(mfd=2.5),
    )


_CATALOG: dict[str, tuple[str, Callable[[], Project]]] = {
    "si_strip": ("Si strip 500 x 220 nm", si_strip),
    "si_wire_mpb": ("Si wire vs MPB reference (symmetry)", si_wire_mpb),
    "si_slab": ("Si slab vs exact solution", si_slab),
    "leaky_sin_on_si": ("Leaky SiN slab over Si substrate (PML)", leaky_sin_on_si),
    "width_sweep_crossing": ("Width sweep through a mode crossing", width_sweep_crossing),
    "strip_dispersion": ("Wavelength sweep: group index and dispersion", strip_dispersion),
    "curved_slab": ("Curved slab vs exact bend solution", curved_slab),
    "strip_bend": ("Si strip bend, radius 1.5 um", strip_bend),
    "directional_coupler": ("Directional coupler supermodes", directional_coupler),
    "inverse_taper_tip": ("Fiber edge coupler (inverse taper tip)", inverse_taper_tip),
    "si_rib": ("Si rib waveguide", si_rib),
    "sin_strip": ("SiN strip", sin_strip),
    "algaas_ridge": ("GaAs/AlGaAs ridge", algaas_ridge),
    "tfln_ridge": ("Thin-film LiNbO3 ridge", tfln_ridge),
}


def catalog() -> dict[str, str]:
    """{name: title} for every example."""
    return {k: v[0] for k, v in _CATALOG.items()}


def load(name: str) -> Project:
    """A fresh copy of example `name`."""
    if name not in _CATALOG:
        raise ValueError(f"no example {name!r}; available: {', '.join(_CATALOG)}")
    return _CATALOG[name][1]()


def write_all(folder) -> list[Path]:
    """Save every example as <folder>/<name>.gmode."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in _CATALOG:
        path = folder / f"{name}.gmode"
        load(name).save(path)
        paths.append(path)
    return paths


if __name__ == "__main__":
    for path in write_all(sys.argv[1] if len(sys.argv) > 1 else "examples"):
        print(path)
