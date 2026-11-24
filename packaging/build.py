"""Build the desktop app and wrap it in this platform's installer, in dist/release/:

    macOS    GMode-<version>-macos-<arch>.dmg          drag-to-Applications disk image
    Windows  GMode-<version>-windows-x86_64-setup.exe  Inno Setup installer (per-user, no admin needed)
    Linux    GMode-<version>-linux-x86_64.AppImage     single executable file

    uv run --extra gui --with pyinstaller --with pillow python packaging/build.py [--test] [--skip-app]

--test runs the app's --self-test (a real solve in a worker process) on the packaged result: from the
mounted disk image, from a silent install of the Windows installer, or from the AppImage.
--skip-app reuses an existing dist/GMode build. The release workflow (.github/workflows/release.yml)
runs this on each OS. Windows needs Inno Setup 6 (choco install innosetup); Linux downloads
appimagetool unless APPIMAGETOOL points at one.
"""
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUT = DIST / "release"
ICON = ROOT / "src" / "gmode" / "gui" / "icon.png"
VERSION = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
ARCH = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine().lower()]
APPIMAGETOOL_URL = "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"


def run(*cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def self_test(exe, env=None):
    """The app prints nothing visible on Windows (no console), so the exit code is the verdict."""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", **(env or {})}
    r = subprocess.run([str(exe), "--self-test"], env=env, timeout=600)
    if r.returncode:
        sys.exit(f"self-test failed for {exe} (exit code {r.returncode})")
    print("self-test passed:", exe, flush=True)


def build_app():
    run(sys.executable, "-m", "PyInstaller", ROOT / "packaging" / "gmode.spec", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", ROOT / "build", cwd=ROOT)


# ---- macOS ------------------------------------------------------------------------------------
def macos(test):
    out = OUT / f"GMode-{VERSION}-macos-{ARCH}.dmg"
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "GMode"
        stage.mkdir()
        run("ditto", DIST / "GMode.app", stage / "GMode.app")  # ditto keeps the bundle's symlinks and signature
        (stage / "Applications").symlink_to("/Applications")
        out.unlink(missing_ok=True)
        run("hdiutil", "create", "-volname", f"GMode {VERSION}", "-srcfolder", stage, "-format", "UDZO", "-ov", out)
    if test:
        with tempfile.TemporaryDirectory() as mnt:
            run("hdiutil", "attach", out, "-nobrowse", "-readonly", "-mountpoint", mnt)
            try:
                self_test(Path(mnt) / "GMode.app" / "Contents" / "MacOS" / "GMode")
            finally:
                run("hdiutil", "detach", mnt, "-force")
    return out


# ---- Windows ----------------------------------------------------------------------------------
def windows(test):
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if not Path(iscc).exists():
        sys.exit("Inno Setup 6 not found: choco install innosetup")
    from PIL import Image

    ico = ROOT / "build" / "gmode.ico"
    ico.parent.mkdir(exist_ok=True)
    Image.open(ICON).save(ico, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    base = f"GMode-{VERSION}-windows-{ARCH}-setup"
    run(iscc, f"/DAppVersion={VERSION}", f"/DSourceDir={DIST / 'GMode'}", f"/DOutputDir={OUT}",
        f"/DOutputBase={base}", f"/DIconFile={ico}", ROOT / "packaging" / "gmode.iss")
    out = OUT / f"{base}.exe"
    if test:
        target = Path(tempfile.mkdtemp()) / "GMode"
        run(out, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", f"/DIR={target}",
            "/MERGETASKS=!assoc")
        self_test(target / "GMode.exe")
        run(target / "unins000.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    return out


# ---- Linux ------------------------------------------------------------------------------------
DESKTOP = """[Desktop Entry]
Type=Application
Name=GMode
GenericName=Waveguide mode solver
Comment=Finite-difference eigenmode solver for optical waveguides
Exec=GMode %f
Icon=gmode
Terminal=false
Categories=Science;Physics;
"""

APPRUN = """#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/opt/gmode/GMode" "$@"
"""


def linux(test):
    tool = os.environ.get("APPIMAGETOOL")
    if not tool:
        tool = ROOT / "build" / "appimagetool.AppImage"
        if not tool.exists():
            tool.parent.mkdir(exist_ok=True)
            print("downloading appimagetool", flush=True)
            urllib.request.urlretrieve(APPIMAGETOOL_URL, tool)
            tool.chmod(0o755)
    appdir = ROOT / "build" / "GMode.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(DIST / "GMode", appdir / "opt" / "gmode", symlinks=True)
    (appdir / "AppRun").write_text(APPRUN)
    (appdir / "AppRun").chmod(0o755)
    (appdir / "gmode.desktop").write_text(DESKTOP)
    shutil.copy(ICON, appdir / "gmode.png")
    shutil.copy(ICON, appdir / ".DirIcon")
    out = OUT / f"GMode-{VERSION}-linux-{ARCH}.AppImage"
    env = {**os.environ, "ARCH": ARCH, "APPIMAGE_EXTRACT_AND_RUN": "1"}  # no FUSE needed (CI containers lack it)
    run(tool, appdir, out, env=env)
    if test:
        self_test(out, env={"APPIMAGE_EXTRACT_AND_RUN": "1"})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--test", action="store_true", help="self-test the packaged app")
    ap.add_argument("--skip-app", action="store_true", help="reuse an existing dist/GMode build")
    args = ap.parse_args()
    if not args.skip_app:
        build_app()
    OUT.mkdir(parents=True, exist_ok=True)
    package = {"darwin": macos, "win32": windows}.get(sys.platform, linux)
    path = package(args.test)
    print(f"\nbuilt {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.0f} MB)")
