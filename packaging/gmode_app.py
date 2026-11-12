"""Entry point for the frozen desktop app (PyInstaller).

freeze_support() runs before the GUI is imported: in a frozen app each solver worker is a new
process of this same executable, and it must become a worker, not a second window.
"""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from gmode.gui.app import main

    sys.exit(main())
