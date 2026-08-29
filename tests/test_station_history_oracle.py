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

TESTS_DIR = Path(__file__).resolve().parent
SNAPSHOTS = TESTS_DIR / "_oracle_outputs" / "station_history"

#: Stations spanning the shapes the renderer has to survive: RHOF (3 clean
#: eras), AUST (the high-session-count fixture), VMEY (separate non-zero
#: monument and antenna eccentricity).
ORACLE_STATIONS = ["RHOF", "AUST", "VMEY"]

#: Both output modes. `raw_format=True` is the `--raw` branch; `False` is the
#: DEFAULT `--format table` path — and the one that is currently broken, so a
#: fixture set covering only `--raw` would have missed the entire bug.
RAW_MODES = [False, True]


def _capture(fn, station, raw_format: bool, **kwargs) -> str:
    """Return everything ``fn`` prints. It renders to stdout and returns None.

    ``**kwargs`` is forwarded so a caller can vary ``language`` — omitting it
    exercises the DEFAULT, which is a distinct case worth reaching explicitly
    rather than by passing the default's value.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(station, raw_format=raw_format, loglevel=logging.CRITICAL, **kwargs)
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
@pytest.mark.parametrize("raw_format", RAW_MODES, ids=["table", "raw"])
@pytest.mark.parametrize("station", ORACLE_STATIONS)
def test_the_route_tosGPS_takes_renders_and_agrees(station: str, raw_format: bool) -> None:
    """The INVERSION of this file's original crash test — and F2 step 2's proof.

    Before the fix this asserted ``pytest.raises((ValueError, IndexError))``:
    ``tosGPS``'s ``PrintTOS --format table`` reached the legacy copy, which
    raised for 8/8 stations. It was written as an ordinary test rather than an
    ``xfail`` precisely so the fix could not land while leaving the crash in
    place — an xfail that starts passing is silent.

    It now asserts the two things the fix has to deliver together:

    1. the route ``tosGPS`` actually takes renders at all, on BOTH modes;
    2. it byte-equals the route ``__init__._LAZY_EXPORTS`` publishes.

    (2) is what makes this a unification rather than two copies that happen to
    agree today: the assertion fails the moment they diverge again.
    """
    import tostools.gps_metadata_functions as top_level
    from tostools.legacy import gps_metadata_functions as legacy

    st = _station(station)
    via_tosgps = _capture(legacy.print_station_history, st, raw_format)
    via_package = _capture(top_level.print_station_history, st, raw_format)

    _assert_rendered(via_tosgps, station, raw_format)
    assert via_tosgps == via_package, (
        f"{station}: the tosGPS route and the package export have diverged "
        f"again — F2 step 2 unified them onto one implementation"
    )


@pytest.mark.vcr
def test_the_default_contact_language_is_unchanged_from_before_the_fix() -> None:
    """Unifying is a CRASH fix; it must not silently re-language operator output.

    The working implementation rendered contacts in English (``Role``/``Name``,
    ``.title()``-ed ``role``); the copy ``tosGPS`` executed rendered them in
    Icelandic (``Hlutverk``/``Nafn``, raw ``role_is``). Taking the working copy
    wholesale would have changed every operator's ``--raw`` output as a side
    effect of fixing a crash — output people diff against runbooks.

    So the default stays Icelandic and English is opt-in. This pins the
    default; `test_english_contact_language` pins that the option works.
    """
    import tostools.gps_metadata_functions as top_level

    out = _capture(top_level.print_station_history, _station("RHOF"), raw_format=True)
    assert "Hlutverk" in out and "Nafn" in out, (
        "the default contact table is no longer Icelandic — that is a "
        "user-visible change to tosGPS output, not a refactor"
    )
    assert "Eigandi" in out, "role_is values are no longer shown by default"
    assert "Role      Name" not in out, "the English header leaked into the default"


@pytest.mark.vcr
def test_english_contact_language() -> None:
    """``--lang en`` selects the English TOS role field, headers included.

    Asserts the VALUES change too, not just the headers: `role` and `role_is`
    are different TOS fields, so a language switch that moved the headers but
    kept reading `role_is` would look right and show Icelandic data under
    English labels.
    """
    import tostools.gps_metadata_functions as top_level

    out = _capture(
        top_level.print_station_history,
        _station("RHOF"),
        raw_format=True,
        language="en",
    )
    assert "Role" in out and "Name" in out, "English headers missing"
    assert "Owner" in out, "the English `role` values were not used"
    assert "Hlutverk" not in out, "Icelandic header survived --lang en"
    assert "Eigandi" not in out, "Icelandic role_is values survived --lang en"


# ---------------------------------------------------------------------------
# KNOWN COVERAGE GAP — the hash-seed non-determinism has NO dedicated guard.
#
# While building this file, AUST's snapshot passed twice and failed the third
# time from a different process. Cause: `device_attribute_history`
# (`gps_metadata_qc.py`) iterated an unordered `set` of sub-session windows.
# Windows are visited in arbitrary order and later writes overwrite earlier
# ones, so which attribute VALUE landed in which window depended on
# PYTHONHASHSEED, and `print_station_history` renders those attributes as its
# device-table columns. The twin `sub_sessions` set later in the SAME function
# was already sorted — the fix had been applied to one of two identical sites.
# Published site logs were never affected (that renderer sorts sessions
# itself), which is why something this visible survived unnoticed.
#
# FIXED (the sort is now on both sites) and verified by hand: AUST renders
# identically under PYTHONHASHSEED 0-5, and `test_sitelog_oracle` passes
# unchanged, proving no published site log moved.
#
# But it is NOT guarded, and that is recorded here rather than papered over.
# THREE candidate guards were written and each was discarded after being shown
# to prove nothing — every one of them passed with the fix reverted:
#
#   1. "sub-sessions come back in date order" — they do either way; the
#      function's output is already canonical.
#   2. "permute the input attribute order" — all 120 permutations produce one
#      identical result. Input order is not what varies; hash seed is.
#   3. "pickle the station and re-render in subprocesses under 4 seeds" — the
#      composition happens in the TEST process, so the non-determinism is
#      already baked into the pickled dict before the subprocess starts.
#
# A real guard has to re-run the COMPOSITION (not the render) across processes.
# That is what `test_the_render_is_not_hash_seed_dependent` below does — the
# raw TOS payloads are already in the cassette, so the subprocess replays it
# and composes there. CONFIRMED to catch the real regression: with the sort
# reverted, seed 1 renders differently from seeds 0/2/3/4/5.
# ---------------------------------------------------------------------------

#: The cassette the determinism guard replays. It belongs to another test in
#: this file — a deliberate, named coupling: the guard needs RAW TOS payloads
#: for a station with enough attribute periods to expose the bug, and recording
#: a second identical cassette would only double the maintenance.
_AUST_CASSETTE = (
    TESTS_DIR
    / "cassettes"
    / "test_station_history_oracle"
    / "test_working_implementation_matches_snapshot[AUST-table].yaml"
)

#: Seeds to compose under. WHICH seeds expose an unsorted iteration is
#: data-dependent — with the fix reverted exactly one of 0-5 (seed 1) diverged
#: — so this samples rather than proves. Widening costs ~1.5 s per seed.
_HASH_SEEDS = ("0", "1", "2", "3", "4", "5")


def test_the_render_is_not_hash_seed_dependent(tmp_path) -> None:
    """The composition must not depend on PYTHONHASHSEED. Checked across processes.

    See the block comment above for the bug. This is the guard the three
    cheaper attempts listed there could not be: set iteration order is fixed
    for the life of an interpreter, so nothing in-process can vary it, and
    pickling the COMPOSED station bakes the non-determinism in before the
    subprocess starts. Replaying the cassette moves the composition into the
    subprocess, which is the whole trick.

    `record_mode="none"` means any request absent from the cassette raises, so
    this cannot quietly reach production TOS despite running outside the
    suite's socket guard.
    """
    import subprocess
    import sys
    import textwrap

    assert _AUST_CASSETTE.exists(), (
        f"cassette missing: {_AUST_CASSETTE}\n"
        f"This guard replays another test's cassette; re-record with\n"
        f"  pytest tests/test_station_history_oracle.py --record-mode=once"
    )

    driver = tmp_path / "compose_and_render.py"
    driver.write_text(
        textwrap.dedent(
            """
            import contextlib, hashlib, io, logging, sys
            import vcr
            from tostools import gps_metadata_qc as gpsqc
            import tostools.gps_metadata_functions as m

            with vcr.use_cassette(
                sys.argv[1],
                record_mode="none",
                match_on=["method", "scheme", "host", "path", "query", "body"],
                allow_playback_repeats=True,
            ):
                station = gpsqc.gps_metadata(
                    "AUST", gpsqc.URL_REST_TOS, loglevel=logging.CRITICAL
                )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                m.print_station_history(
                    station, raw_format=False, loglevel=logging.CRITICAL
                )
            out = buf.getvalue()
            assert out.strip(), "rendered nothing"
            sys.stderr.write(hashlib.sha1(out.encode()).hexdigest())
            """
        )
    )

    digests = {}
    for seed in _HASH_SEEDS:
        proc = subprocess.run(
            [sys.executable, str(driver), str(_AUST_CASSETTE)],
            capture_output=True,
            text=True,
            env={
                "PYTHONHASHSEED": seed,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "PYTHONPATH": os.pathsep.join(sys.path),
            },
        )
        assert proc.returncode == 0, (
            f"compose+render failed under PYTHONHASHSEED={seed}:\n"
            f"{proc.stderr[-2000:]}"
        )
        digests[seed] = proc.stderr.strip()[:40]
        assert digests[seed], f"seed {seed} produced no digest"

    assert len(set(digests.values())) == 1, (
        f"composition differs across hash seeds {digests} — an unordered set "
        f"is back in the device_attribute_history chain. Every snapshot in "
        f"this file is now flaky rather than wrong, and operator table columns "
        f"change run to run."
    )



@pytest.mark.vcr
def test_an_unknown_language_falls_back_rather_than_raising() -> None:
    """A bad ``--lang`` must not take down a metadata dump.

    argparse constrains the CLI to is/en, but the function is public and
    reachable from `from tostools import print_station_history`, so the
    fallback is the library-level contract.
    """
    import tostools.gps_metadata_functions as top_level

    st = _station("RHOF")
    out = _capture(top_level.print_station_history, st, raw_format=True, language="xx")
    default = _capture(top_level.print_station_history, st, raw_format=True)
    assert out == default, "an unknown language did not fall back to the default"
