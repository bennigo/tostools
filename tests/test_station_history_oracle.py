"""Output oracle for ``print_station_history`` — F2 step 2's gate.

``print_station_history`` is the LAST genuine two-live-copies fork in the
package, and the only one where both copies are reachable in production:

* ``tosGPS`` executes the **legacy** copy (``tosGPS.py:1206``, the
  ``PrintTOS --format table`` path);
* ``__init__._LAZY_EXPORTS`` publishes the **top-level** copy, so
  ``from tostools import print_station_history`` — the name every editable
  sibling would reach for — resolves to the other one.

Unlike ``site_log`` and ``print_station_info`` (F2 step 1), the live copy here
is **not** the one to keep. Established by running both, not by reading them:

    the legacy copy CRASHES on the default ``--format table`` path for every
    station tried (8/8: RHOF, AUST, VMEY, ISAK, THOB, ELDC, AKUR, HOFN),
    with ``ValueError: Unknown format code 'f' for object of type 'str'`` or
    ``IndexError``, while the top-level copy renders all of them.

``tos PrintTOS RHOF --format table`` exits 1 after printing a partial table.
The top-level rewrite carries the fix — its own comment says "Use simple
tabulate format for regular output - avoiding string formatting bugs" — and
has been sitting in the copy nobody executes. That is this repo's documented
orphaned-abstraction failure mode in its most expensive form: the fix exists,
in the module that never runs.

So the direction of unification is **inverted** for this function relative to
step 1, which is exactly why the architecture review insists liveness be
established per function by call site rather than per module.

This file locks the WORKING (top-level) output as the target before any src
change, and records the crash so it cannot silently return.

Re-record / re-snapshot — delete the cassette first, ``--record-mode=once``
only records when the file is ABSENT (see ``test_sitelog_oracle`` for the full
trap)::

    rm tests/cassettes/test_station_history_oracle/<test>.yaml
    pytest tests/test_station_history_oracle.py --record-mode=once
    STATION_HISTORY_ORACLE_UPDATE=1 pytest tests/test_station_history_oracle.py
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
from pathlib import Path

import pytest

from tostools import gps_metadata_qc as gpsqc

SNAPSHOTS = Path(__file__).resolve().parent / "_oracle_outputs" / "station_history"

#: Stations spanning the shapes the renderer has to survive: RHOF (3 clean
#: eras), AUST (the high-session-count fixture), VMEY (separate non-zero
#: monument and antenna eccentricity).
ORACLE_STATIONS = ["RHOF", "AUST", "VMEY"]

#: Both output modes. `raw_format=True` is the `--raw` branch; `False` is the
#: DEFAULT `--format table` path — and the one that is currently broken, so a
#: fixture set covering only `--raw` would have missed the entire bug.
RAW_MODES = [False, True]


def _capture(fn, station, raw_format: bool) -> str:
    """Return everything ``fn`` prints. It renders to stdout and returns None."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(station, raw_format=raw_format, loglevel=logging.CRITICAL)
    return buf.getvalue()


def _station(sid: str):
    station = gpsqc.gps_metadata(sid, gpsqc.URL_REST_TOS, loglevel=logging.CRITICAL)
    assert station, f"{sid}: no TOS metadata — re-record the cassette"
    return station


def _assert_rendered(out: str, sid: str, raw_format: bool) -> None:
    """Structural floor, so a byte-compare cannot be satisfied by a stub.

    Same reasoning as the site-log oracle: two equal strings are equal even
    when both are wrong. A render that died early still produces output (the
    live crash emits ~1,270 characters before raising), so "non-empty" proves
    nothing on its own — these assertions are what a truncated render fails.
    """
    assert out, f"{sid}: nothing was printed"
    # The station attribute table always renders first.
    assert "marker" in out, f"{sid}: station attribute header missing"
    # Every fixture station has real device history; the device table is the
    # part the crash truncated, so its absence is the failure to catch.
    for subtype in ("gnss_receiver", "antenna"):
        assert subtype in out, (
            f"{sid} (raw_format={raw_format}): no {subtype!r} in the device "
            f"table — the render was truncated before device history"
        )
    assert out.count("\n") > 10, f"{sid}: implausibly short render"


@pytest.mark.vcr
@pytest.mark.parametrize("raw_format", RAW_MODES, ids=["table", "raw"])
@pytest.mark.parametrize("station", ORACLE_STATIONS)
def test_working_implementation_matches_snapshot(station: str, raw_format: bool) -> None:
    """Lock the output F2 step 2 will unify ONTO.

    The snapshot is taken from the TOP-LEVEL copy — the one that works — so
    that when ``tosGPS`` is repointed at it, "did the fix change anything
    else?" is answerable byte-for-byte rather than by eye.
    """
    import tostools.gps_metadata_functions as top_level

    out = _capture(top_level.print_station_history, _station(station), raw_format)
    _assert_rendered(out, station, raw_format)

    mode = "raw" if raw_format else "table"
    snapshot_path = SNAPSHOTS / f"{station}_{mode}.txt"

    if os.environ.get("STATION_HISTORY_ORACLE_UPDATE"):
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(out, encoding="utf-8")
        pytest.skip(f"snapshot rewritten: {snapshot_path}")
    if not snapshot_path.exists():
        pytest.fail(
            f"Snapshot missing: {snapshot_path}\n"
            f"  STATION_HISTORY_ORACLE_UPDATE=1 pytest "
            f"tests/test_station_history_oracle.py"
        )
    assert out == snapshot_path.read_text(encoding="utf-8"), (
        f"{station} ({mode}): rendered station history differs from its snapshot"
    )


@pytest.mark.vcr
@pytest.mark.parametrize("station", ORACLE_STATIONS)
def test_the_live_default_path_is_broken(station: str) -> None:
    """RECORDS A PRODUCTION BUG — this test is expected to be INVERTED by the fix.

    ``tosGPS``'s ``PrintTOS --format table`` reaches the legacy copy, which
    raises on every station tried. Pinning it here means: (a) the bug is
    reproduced in the suite rather than asserted in a commit message, and
    (b) when F2 step 2 repoints the call site, this test must be rewritten to
    assert success — so the fix cannot land while quietly leaving the crash in
    place, and the crash cannot creep back unnoticed afterwards.

    Deliberately NOT an ``xfail``: an xfail that starts passing is silent by
    default, and this needs to be loud in both directions.
    """
    from tostools.legacy import gps_metadata_functions as legacy

    with pytest.raises((ValueError, IndexError)):
        _capture(legacy.print_station_history, _station(station), raw_format=False)


@pytest.mark.vcr
@pytest.mark.parametrize("station", ORACLE_STATIONS)
def test_both_copies_agree_on_the_raw_path(station: str) -> None:
    """Scopes the divergence: ``--raw`` is NOT where the two copies differ badly.

    Both render it without raising, so if the outputs were identical here the
    fork would be cosmetic. They are not — this pins the fact that the
    difference is real on BOTH paths, so repointing the call site is a
    user-visible output change on ``--raw`` too, not only on the broken
    default. That is the thing to check against a runbook before shipping.
    """
    import tostools.gps_metadata_functions as top_level
    from tostools.legacy import gps_metadata_functions as legacy

    st = _station(station)
    legacy_out = _capture(legacy.print_station_history, st, raw_format=True)
    top_out = _capture(top_level.print_station_history, st, raw_format=True)

    _assert_rendered(legacy_out, station, True)
    _assert_rendered(top_out, station, True)
    assert legacy_out != top_out, (
        "the two copies now agree on the raw path — if that is intended, this "
        "test has done its job and should be replaced by a byte-equality "
        "assertion rather than deleted"
    )
