import sys

from .app import main

# the guard matters: solver workers are spawned processes that re-import the main module
if __name__ == "__main__":
    sys.exit(main())
