"""Library code must RAISE on an unreachable TOS, never ``sys.exit(1)``.

``gps_metadata_qc`` is imported by 11 modules, including ``rinex/corrector.py``,
``rinex/validator.py`` and ``api/tos_client.py``. Calling ``sys.exit(1)`` from
inside one of its helpers killed the entire process on a single transient TOS
blip — and did it as ``SystemExit``, a ``BaseException`` that sails straight
past ``except Exception``, so callers could not even intercept it without
naming ``SystemExit`` explicitly. ``receivers.rinex.converter_base`` had to do
exactly that, and says so in a comment.

The replacement is ``TOSConnectionError``, which subclasses builtin
``ConnectionError`` (hence ``OSError``) deliberately: downstream transport
handlers that already catch ``OSError`` keep working untouched, while callers
who want to be specific can catch the typed error.
"""

from __future__ import annotations

import pytest
import requests

from tostools import gps_metadata_qc as gpsqc
from tostools.exceptions import TOSConnectionError, TOSError


def test_hierarchy_lands_in_existing_transport_handlers():
    """The base classes are load-bearing, not decoration.

    ``receivers.rinex.converter_base`` catches ``OSError`` and converts it to
    its own ``NetworkUnavailableError`` (with retries). If this ever stops
    being an ``OSError``, that handler silently stops catching it and a
    re-rinex run dies on an unhandled exception instead of retrying.
    """
    exc = TOSConnectionError("unreachable")
    assert isinstance(exc, TOSError)
    assert isinstance(exc, ConnectionError)
    assert isinstance(exc, OSError)
    assert not isinstance(exc, SystemExit)


def test_search_station_raises_instead_of_exiting(monkeypatch):
    def _boom(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(gpsqc.requests, "post", _boom)

    # SystemExit is NOT an Exception subclass, so this pytest.raises would not
    # catch the old behaviour — the test would error out instead of passing.
    with pytest.raises(TOSConnectionError) as info:
        gpsqc.search_station("REYK", domains="geophysical")

    # The original transport error is preserved for diagnosis.
    assert isinstance(info.value.__cause__, requests.ConnectionError)


def test_caller_catching_oserror_still_intercepts(monkeypatch):
    """Simulates receivers.rinex.converter_base's handler order."""

    def _boom(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(gpsqc.requests, "post", _boom)

    caught_by = None
    try:
        gpsqc.search_station("REYK", domains="geophysical")
    except SystemExit:  # pragma: no cover — the bug this file exists to prevent
        caught_by = "SystemExit"
    except OSError:
        caught_by = "OSError"
    except Exception:  # pragma: no cover
        caught_by = "Exception"

    assert caught_by == "OSError"


def test_no_sys_exit_left_in_the_module():
    """Guard the guard: no new ``sys.exit`` may creep back into this library."""
    import inspect

    source = inspect.getsource(gpsqc)
    offenders = [
        line.strip()
        for line in source.splitlines()
        if "sys.exit(" in line and not line.lstrip().startswith("#")
    ]
    assert offenders == [], f"library code must raise, not exit: {offenders}"
