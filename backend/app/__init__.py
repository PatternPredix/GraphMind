"""GraphMind backend package.

Enforce the supported interpreter floor as early as possible: importing any part
of the app on Python < 3.10 fails fast with a clear message rather than a
confusing error deeper in a dependency.
"""
import sys

if sys.version_info < (3, 10):
    raise RuntimeError(
        "GraphMind requires Python 3.10 or newer, but is running on "
        f"{sys.version_info.major}.{sys.version_info.minor}. "
        "Recreate the virtual environment with Python 3.10+ "
        "(the installers use 3.12)."
    )
