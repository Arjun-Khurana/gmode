## Install

| System | Download | |
|---|---|---|
| macOS, Apple silicon | `GMode-*-macos-arm64.dmg` | open it and drag GMode to Applications |
| macOS, Intel | `GMode-*-macos-x86_64.dmg` | same |
| Windows 10/11 | `GMode-*-windows-x86_64-setup.exe` | run it; no administrator rights needed |
| Linux (x86_64) | `GMode-*-linux-x86_64.AppImage` | `chmod +x` it and run it |
| Python | `gmode-*.whl` | `pip install "gmode-<version>-py3-none-any.whl[gui]"` |

The apps aren't code-signed yet, so the first launch needs one extra step:

* **macOS** says GMode "cannot be opened" or "is damaged": open System Settings › Privacy & Security
  and click *Open Anyway*, or run `xattr -dr com.apple.quarantine /Applications/GMode.app` once.
* **Windows** SmartScreen says "Windows protected your PC": click *More info*, then *Run anyway*.
* **Linux**: the AppImage needs FUSE 2 (`sudo apt install libfuse2` on Ubuntu 22.04+, or run it with
  `--appimage-extract-and-run`), and Qt's X11 cursor library (`sudo apt install libxcb-cursor0`).
