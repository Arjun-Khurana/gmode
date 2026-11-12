"""Project tree: simulation settings, materials and structures."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QMessageBox, QTreeWidget, QTreeWidgetItem

from .document import ProjectDocument

ROLE = Qt.ItemDataRole.UserRole


class ProjectTree(QTreeWidget):
    addStructureRequested = Signal(str)  # "rectangle" | "circle" | "polygon" | "trapezoid"
    addMaterialRequested = Signal(str)  # "library" | "constant" | "file"

    def __init__(self, doc: ProjectDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setRootIsDecorated(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemSelectionChanged.connect(self._selected)
        self._updating = False
        doc.changed.connect(self.rebuild)
        doc.selectionChanged.connect(self._sync_selection)
        self.rebuild()

    def rebuild(self):
        self._updating = True
        self.clear()
        p = self.doc.project
        sim = QTreeWidgetItem(self, ["Simulation"])
        sim.setData(0, ROLE, ("project",))
        for key, label in (("domain", "Domain"), ("mesh", "Mesh"), ("boundaries", "Boundaries"), ("solver", "Solver"),
                           ("fiber", "Fiber coupling")):
            it = QTreeWidgetItem(sim, [label])
            it.setData(0, ROLE, (key,))
        mats = QTreeWidgetItem(self, [f"Materials ({len(p.materials)})"])
        mats.setData(0, ROLE, ("materials-root",))
        for name, m in p.materials.items():
            label = name + ("  (background)" if name == p.background else "")
            it = QTreeWidgetItem(mats, [label])
            it.setData(0, ROLE, ("material", name))
            it.setToolTip(0, m.description or m.kind)
        structs = QTreeWidgetItem(self, [f"Structures ({len(p.structures)})"])
        structs.setData(0, ROLE, ("structures-root",))
        structs.setToolTip(0, "Later structures are drawn on top of earlier ones")
        for i, s in enumerate(p.structures):
            it = QTreeWidgetItem(structs, [f"{s.name}  [{s.material}]"])
            it.setData(0, ROLE, ("structure", i))
        self.expandAll()
        self._updating = False
        self._sync_selection(self.doc.selection)

    def _item_for(self, sel):
        it = self.invisibleRootItem()
        stack = [it.child(i) for i in range(it.childCount())]
        while stack:
            x = stack.pop()
            if x.data(0, ROLE) == sel:
                return x
            stack.extend(x.child(i) for i in range(x.childCount()))
        return None

    def _sync_selection(self, sel):
        self._updating = True
        self.clearSelection()
        it = self._item_for(sel) if sel else None
        if it is not None:
            it.setSelected(True)
            self.scrollToItem(it)
        self._updating = False

    def _selected(self):
        if self._updating:
            return
        items = self.selectedItems()
        key = items[0].data(0, ROLE) if items else None
        if key and key[0].endswith("-root"):
            key = None
        self.doc.select(key)

    def _menu(self, pos):
        it = self.itemAt(pos)
        key = it.data(0, ROLE) if it else None
        menu = QMenu(self)
        if key and key[0] in ("structures-root", "structure"):
            for kind in ("rectangle", "circle", "trapezoid", "polygon"):
                menu.addAction(f"Add {kind}", lambda k=kind: self.addStructureRequested.emit(k))
        if key and key[0] == "structure":
            i = key[1]
            menu.addSeparator()
            menu.addAction("Duplicate", lambda: self.doc.duplicate_structure(i))
            menu.addAction("Bring forward", lambda: self.doc.move_structure(i, +1))
            menu.addAction("Send backward", lambda: self.doc.move_structure(i, -1))
            menu.addAction("Delete", lambda: self.doc.remove_structure(i))
        if key and key[0] in ("materials-root", "material"):
            menu.addAction("Add from library...", lambda: self.addMaterialRequested.emit("library"))
            menu.addAction("Add constant index", lambda: self.addMaterialRequested.emit("constant"))
            menu.addAction("Import n,k file...", lambda: self.addMaterialRequested.emit("file"))
        if key and key[0] == "material":
            name = key[1]
            menu.addSeparator()
            menu.addAction("Use as background", lambda: self._set_background(name))
            menu.addAction("Delete", lambda: self._delete_material(name))
        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _set_background(self, name):
        d = self.doc.project.model_dump()
        d["background"] = name
        self.doc.edit(d, f"Background {name}")

    def _delete_material(self, name):
        try:
            self.doc.remove_material(name)
        except ValueError as e:
            QMessageBox.warning(self, "Cannot delete material", str(e))
