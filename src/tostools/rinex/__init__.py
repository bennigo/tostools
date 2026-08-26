"""
RINEX file processing modules.

This package contains modules for reading, validating, and editing RINEX files,
as well as comparing RINEX data with TOS metadata.

Import cost
-----------
These re-exports are resolved **lazily** (PEP 562). Eagerly importing
``correct_rinex_from_tos`` here meant that touching *anything* in this package
pulled in ``corrector`` -> ``gps_metadata_qc`` -> pandas, numpy and requests.

That fell hardest on the cheapest thing here: ``receivers`` imports
``domes_or_skip`` — a compiled regex and a branch — on a hot path, and paid
~0.6 s of pandas/numpy import per process for the privilege. It also meant a
pyproj or pandas problem surfaced as an import-time failure of DOMES
validation, which touches neither.

The public surface is unchanged: ``from tostools.rinex import X`` resolves
exactly as before, just on first access.
"""

import importlib
from typing import Any

# Exported name -> defining module.
_LAZY_EXPORTS = {
    "correct_rinex_from_tos": ".corrector",
    "domes_or_skip": ".domes",
    "is_iers_domes": ".domes",
    "get_rinex_labels": ".reader",
    "read_rinex_file": ".reader",
    "read_rinex_header": ".reader",
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    """Resolve a re-exported name on first access (PEP 562)."""
    try:
        source = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    value = getattr(importlib.import_module(source, __name__), name)
    globals()[name] = value  # cache: __getattr__ is not consulted again
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
