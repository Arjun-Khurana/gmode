# PyInstaller spec for the GMode desktop app.
#   uv run --extra gui --with pyinstaller pyinstaller packaging/gmode.spec --noconfirm
# Produces dist/GMode.app on macOS (dist/GMode/ elsewhere). Check it with:
#   dist/GMode.app/Contents/MacOS/GMode --self-test
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "packaging" / "gmode_app.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("gmode", includes=["gui/fonts/*"]),
    hiddenimports=["pymetis"],
    # not used by the app: the optional MPB backend, matplotlib helpers, and heavy Qt modules
    excludes=["meep", "matplotlib", "mpmath", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GMode", console=False,
          argv_emulation=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="GMode", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="GMode.app", bundle_identifier="org.gmode.GMode",
                 info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "0.1.0",
                             "CFBundleDocumentTypes": [{"CFBundleTypeName": "GMode project",
                                                        "CFBundleTypeExtensions": ["gmode"],
                                                        "CFBundleTypeRole": "Editor"}]})
