"""The open project: current state, undo history, file path and latest results.

Every edit replaces the project with a validated copy and is pushed onto the
undo stack as a before/after snapshot, so undo/redo is exact and an invalid
edit never reaches the model.
"""
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QUndoCommand, QUndoStack

import gmode as gm
from gmode.project import Project
from gmode.results import ModeSet

# selection keys: ("project",), ("domain",), ("mesh",), ("boundaries",), ("solver",),
# ("material", name), ("structure", index), or None
Selection = Optional[tuple]
SECTIONS = ("domain", "mesh", "boundaries", "solver", "fiber")


def default_project() -> Project:
    """A silicon strip waveguide in oxide, a sensible starting point."""
    return Project(
        name="si_strip",
        wavelength=1.55,
        materials={"Si": "Si", "SiO2": "SiO2"},
        background="SiO2",
        structures=[gm.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
        domain=gm.Domain(size=(3.0, 2.0)),
        mesh=gm.Mesh(dx=0.02, dy=0.02),
        boundaries=gm.Boundaries(),
        solver=gm.SolverSettings(num_modes=4),
    )


class _Snapshot(QUndoCommand):
    def __init__(self, doc: "ProjectDocument", before: dict, after: dict, text: str):
        super().__init__(text)
        self.doc, self.before, self.after = doc, before, after

    def redo(self):
        self.doc._set(self.after)

    def undo(self):
        self.doc._set(self.before)


class ProjectDocument(QObject):
    changed = Signal()  # the project was edited, undone, redone or replaced
    selectionChanged = Signal(object)
    resultsChanged = Signal()
    titleChanged = Signal()

    def __init__(self, project: Optional[Project] = None, parent=None):
        super().__init__(parent)
        self.undo_stack = QUndoStack(self)
        # a bound slot, not a lambda: Qt drops it when this object is destroyed, before the
        # stack (our child) is; a dirty stack emits cleanChanged from its destructor
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self.project: Project = project or default_project()
        self.path: Optional[Path] = None
        self.results: Optional[ModeSet] = None
        self.results_stale = False
        self.selection: Selection = None

    @Slot(bool)
    def _on_clean_changed(self, _clean: bool):
        self.titleChanged.emit()

    # ---- state ----------------------------------------------------------------------------
    def _set(self, data: dict):
        self.project = Project.model_validate(data)
        if self.results is not None:
            self.results_stale = True
        self._fix_selection()
        self.changed.emit()

    def edit(self, new: Project | dict, text: str):
        """Replace the project with `new` (validated) as one undoable step. Raises ValueError if invalid."""
        before = self.project.model_dump()
        after = Project.model_validate(new if isinstance(new, dict) else new.model_dump()).model_dump()
        if after == before:
            return
        self.undo_stack.push(_Snapshot(self, before, after, text))

    def replace(self, project: Project, path: Optional[Path] = None):
        """Start over with a new or loaded project (clears history and results)."""
        self.undo_stack.clear()
        self.project = project
        self.path = Path(path) if path else None
        self.results, self.results_stale = None, False
        self.selection = None
        self.undo_stack.setClean()
        self.changed.emit()
        self.resultsChanged.emit()
        self.selectionChanged.emit(None)
        self.titleChanged.emit()

    @property
    def dirty(self) -> bool:
        return not self.undo_stack.isClean()

    @property
    def title(self) -> str:
        name = self.path.name if self.path else "untitled"
        return f"{name}{' *' if self.dirty else ''} - GMode"

    def save(self, path=None):
        path = Path(path) if path else self.path
        if path is None:
            raise ValueError("no file name")
        self.project.save(path)
        self.path = path
        self.undo_stack.setClean()
        self.titleChanged.emit()

    def set_results(self, results: Optional[ModeSet]):
        self.results, self.results_stale = results, False
        self.resultsChanged.emit()

    # ---- selection ------------------------------------------------------------------------
    def select(self, sel: Selection):
        if sel != self.selection:
            self.selection = sel
            self.selectionChanged.emit(sel)

    def _fix_selection(self):
        sel = self.selection
        if sel is None:
            return
        if sel[0] == "structure" and sel[1] >= len(self.project.structures):
            self.select(("structure", len(self.project.structures) - 1) if self.project.structures else None)
        elif sel[0] == "material" and sel[1] not in self.project.materials:
            self.select(None)

    def selected_object(self):
        sel, p = self.selection, self.project
        if sel is None:
            return None
        if sel[0] == "project":
            return p
        if sel[0] in SECTIONS:
            return getattr(p, sel[0])
        if sel[0] == "material":
            return p.materials.get(sel[1])
        if sel[0] == "structure" and sel[1] < len(p.structures):
            return p.structures[sel[1]]
        return None

    # ---- edit helpers ---------------------------------------------------------------------
    def _data(self) -> dict:
        return self.project.model_dump()

    def update_selected(self, changes: dict):
        """Apply field changes to whatever is selected."""
        sel = self.selection
        if sel is None:
            return
        d = self._data()
        if sel[0] == "project":
            d.update(changes)
            text = "Edit project"
        elif sel[0] in SECTIONS:
            d[sel[0]].update(changes)
            text = f"Edit {sel[0]}"
        elif sel[0] == "material":
            d["materials"][sel[1]].update(changes)
            text = f"Edit material {sel[1]}"
        else:
            d["structures"][sel[1]].update(changes)
            text = f"Edit {d['structures'][sel[1]]['name']}"
        self.edit(d, text)

    def update_structure(self, i: int, changes: dict, text: str = "Move structure"):
        d = self._data()
        d["structures"][i].update(changes)
        self.edit(d, text)

    def add_structure(self, structure) -> int:
        d = self._data()
        names = {s["name"] for s in d["structures"]}
        base, k = structure.name, 1
        name = base
        while name in names:
            k += 1
            name = f"{base}{k}"
        d["structures"].append({**structure.model_dump(), "name": name})
        self.edit(d, f"Add {name}")
        i = len(self.project.structures) - 1
        self.select(("structure", i))
        return i

    def remove_structure(self, i: int):
        d = self._data()
        s = d["structures"].pop(i)
        self.edit(d, f"Delete {s['name']}")

    def duplicate_structure(self, i: int):
        s = self.project.structures[i]
        self.add_structure(s.model_copy())

    def move_structure(self, i: int, delta: int):
        """Change drawing order; later structures are drawn on top."""
        j = i + delta
        d = self._data()
        if not 0 <= j < len(d["structures"]):
            return
        d["structures"][i], d["structures"][j] = d["structures"][j], d["structures"][i]
        self.edit(d, "Reorder structures")
        self.select(("structure", j))

    def add_material(self, name: str, material) -> str:
        d = self._data()
        base, k = name, 1
        while name in d["materials"]:
            k += 1
            name = f"{base}_{k}"
        d["materials"][name] = material.model_dump()
        self.edit(d, f"Add material {name}")
        self.select(("material", name))
        return name

    def rename_material(self, old: str, new: str):
        new = new.strip()
        if not new or new == old:
            return
        d = self._data()
        if new in d["materials"]:
            raise ValueError(f"a material named {new!r} already exists")
        d["materials"] = {(new if k == old else k): v for k, v in d["materials"].items()}
        if d["background"] == old:
            d["background"] = new
        for s in d["structures"]:
            if s["material"] == old:
                s["material"] = new
        self.edit(d, f"Rename material {old} to {new}")
        self.select(("material", new))

    def remove_material(self, name: str):
        p = self.project
        users = [s.name for s in p.structures if s.material == name] + (["background"] if p.background == name else [])
        if users:
            raise ValueError(f"material {name!r} is used by: {', '.join(users)}")
        d = self._data()
        del d["materials"][name]
        self.edit(d, f"Delete material {name}")
