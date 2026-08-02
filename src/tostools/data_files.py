"""Locate tostools' shipped data files (attribute catalog, suppressions).

These live at the **repo root** in ``data/`` — deliberately, because operators
edit them: ``attribute_codes.yaml`` encodes which attributes the GPS group
requires, and the ``audit_suppressions/`` files are reviewed and committed
alongside the corrections they silence. Burying them inside the package would
make that editing awkward.

The cost was that they were reachable only from a source checkout. Every module
derived them as ``Path(__file__)/../../..``, which is the repo root for an
editable install (``src/tostools/x.py`` → ``<repo>``) but resolves to
``<venv>/lib/pythonX.Y`` for a wheel — so on rek-d01
``tos audit missing-attributes`` died with::

    No such file or directory: '<venv>/lib/python3.13/data/attribute_codes.yaml'

i.e. the catalog-backed audits only ever worked on a dev box, silently.

The wheel now force-includes ``data/`` as ``tostools/data/`` (see pyproject),
and this resolver checks **repo root first**: in a source checkout the working
copy must win, so an operator editing the catalog sees the effect immediately
rather than being shadowed by a stale installed copy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

#: ``src/tostools/`` — where the wheel puts ``data/`` alongside the modules.
_PACKAGE_DIR = Path(__file__).resolve().parent

#: Repo root for a source/editable checkout (``src/tostools/x.py`` → repo).
_REPO_ROOT = _PACKAGE_DIR.parent.parent


def data_path(*parts: str) -> Path:
    """Resolve a path under the shipped ``data/`` tree.

    Checks the repo-root copy first (a source checkout's edits must win over an
    installed one), then the packaged copy. Returns the repo-root candidate
    when neither exists, so the error message names the canonical location
    rather than some venv internals.
    """
    repo_candidate = _REPO_ROOT.joinpath("data", *parts)
    if repo_candidate.exists():
        return repo_candidate

    packaged = _PACKAGE_DIR.joinpath("data", *parts)
    if packaged.exists():
        return packaged

    return repo_candidate


def data_root() -> Optional[Path]:
    """The ``data/`` directory in use, or ``None`` when neither copy exists."""
    for candidate in (_REPO_ROOT / "data", _PACKAGE_DIR / "data"):
        if candidate.is_dir():
            return candidate
    return None
