"""
tostools: Python toolkit for GPS/GNSS station management and TOS API integration

This package provides tools for:
- GPS metadata quality control and validation (main: tosGPS)
- Processing GPS/GNSS station metadata and RINEX files
- Querying TOS (Technical Operations System) API for Icelandic weather/seismic stations
- XML generation for seismic networks (SC3ML, FDSN StationXML)

Main Components:
- tosGPS: GPS metadata QC tool (primary application)
- tos.py: TOS API client (legacy from TOSTools by Tryggvi Hjörvar)
- GPS processing modules: metadata functions, QC, RINEX processing

Import cost
-----------
These re-exports are resolved **lazily** (PEP 562). They used to be eager::

    from .gps_metadata_functions import print_station_history
    from .gps_metadata_qc import gps_metadata
    from .gps_rinex import *

which meant that importing *anything* under ``tostools`` executed the whole
metadata chain: ``gps_metadata_qc`` builds a module-level ``TOSClient`` against
a hardcoded production URL and constructs two pyproj ``Transformer`` objects at
import, and ``gps_rinex`` pulls in numpy and fortranformat.

The cost lands on consumers that want none of it. ``receivers`` imports
``tostools.rinex.domes.domes_or_skip`` — a pure regex check — on a hot path,
and paid ~0.6 s of unrelated import per process for it. Worse, any pyproj/EPSG
problem became an import-time failure of features that never touch geodesy.

Nothing about the public surface changes: every name that ``from tostools
import X`` resolved before still resolves, including the (accidental) names the
star-import published. They are simply materialised on first access and then
cached in ``globals()``.
"""

import importlib
from typing import Any

__version__ = "0.1.0"
__author__ = "Benedikt Gunnar Ófeigsson, Tryggvi Hjörvar"
__email__ = "bgo@vedur.is"

# Explicitly re-exported names -> the module that defines them.
_LAZY_EXPORTS = {
    "print_station_history": ".gps_metadata_functions",
    "gps_metadata": ".gps_metadata_qc",
}

# Anything else that used to arrive via `from .gps_rinex import *`.
_STAR_SOURCE = ".gps_rinex"

# Legacy TOS functions (from Tryggvi's TOSTools) - temporarily disabled
# from .tos import searchStation, searchDevice

__all__ = [
    "print_station_history",
    "gps_metadata",
    # "searchStation",
    # "searchDevice",
]


def __getattr__(name: str) -> Any:
    """Resolve a re-exported name on first access (PEP 562).

    Submodules (``tostools.rinex``, ``tostools.api``, ...) are unaffected —
    Python imports those through the normal machinery and never reaches here.
    """
    if name.startswith("__"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    source = _LAZY_EXPORTS.get(name, _STAR_SOURCE)
    module = importlib.import_module(source, __name__)
    try:
        value = getattr(module, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    globals()[name] = value  # cache: __getattr__ is not consulted again
    return value


def __dir__() -> list[str]:
    """Include the lazily-resolvable names so tab-completion still works."""
    names = set(globals()) | set(_LAZY_EXPORTS)
    try:
        names |= {
            n
            for n in dir(importlib.import_module(_STAR_SOURCE, __name__))
            if not n.startswith("_")
        }
    except Exception:  # pragma: no cover — never let dir() raise
        pass
    return sorted(names)
