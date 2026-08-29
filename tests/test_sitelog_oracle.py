"""Byte-equality oracle for the IGS site log — the F2 refactor's safety net.

Why this exists
---------------
``legacy/gps_metadata_functions.py`` and its top-level counterpart are a
drifted fork (F2 in ``docs/architecture/legacy-fork-unification-plan.md``).
The ``site_log`` halves differ by +303/-477 lines. Unifying them edits the
renderer that **publishes to M3G**, so a wrong merge is externally visible —
it ships a malformed log to the IGS network, not a red test.

The obvious gate — byte-compare the two implementations against each other —
does **not** work, and it is worth recording why so nobody rebuilds it:

* The top-level ``site_log(station_identifier, loglevel)`` has **no production
  caller and no route to one**. It is not imported by any module in this
  package, is absent from ``__init__._LAZY_EXPORTS``, and cannot arrive via
  the ``_STAR_SOURCE`` fallback (``gps_rinex`` does not bind the name). A
  sweep of every editable sibling in the ``gpslibrary`` env and of ``~/git``
  finds no importer either.
* Its signature cannot express a modern log — no ``report_type``, no
  ``previous_log``, no ``agencies``, no ``monument_number``. Locking its
  output would pin the behaviour of the copy F2 is about to reduce to a
  delegator, and the gate would be born red.

So this oracle locks the **live** renderer against committed snapshots
instead. ``core.site_log.build_site_log`` is the single entry point behind
both publishers (``tosGPS sitelog`` and receivers'
``epos-disseminate --sitelog``), and ``legacy.gps_metadata_functions.site_log``
is the renderer under it. Any F2 change that alters a published byte fails
here, which is the property that actually protects M3G.

What the fixtures buy
---------------------
Each station is present because it exercises a distinct branch of the
renderer, not for coverage arithmetic:

- **RHOF** — three device eras across an Ashtech UZ-12 → Trimble NETR9
  swap, and a real IERS DOMES. Exercises multi-block §3/§4 numbering.
- **AUST** — the high-session-count station (``test_composer_oracle``'s
  "legacy is wrong" fixture, 26 well-ordered sessions). Stresses the
  session→block pipeline hardest.
- **ISAK** — carries a synthetic antenna serial in TOS; §4 must publish the
  ``0000`` placeholder. Guards the rule behind the 2026-08-04 bad publish.
- **VMEY** — monument height and antenna eccentricity are separate and
  non-zero, so §4 "Marker->ARP Up Ecc." is a composite. The station of the
  M3G HTTP 422.

Re-recording and re-snapshotting are deliberately **two** steps, because
they answer different questions ("has TOS changed?" vs "have we accepted a
new published output?")::

    pytest tests/test_sitelog_oracle.py --record-mode=once   # refresh cassettes
    SITELOG_ORACLE_UPDATE=1 pytest tests/test_sitelog_oracle.py

Review the snapshot diff as part of the change — it is the published
artefact.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from pathlib import Path

import pytest

from tostools.core.site_log import build_site_log

SNAPSHOTS = Path(__file__).resolve().parent / "_oracle_outputs" / "sitelog"

#: Stations whose rendered log is locked. See the module docstring for why
#: each one is here; do not add a station without a branch it exercises.
ORACLE_STATIONS = ["RHOF", "AUST", "ISAK", "VMEY"]

#: The renderer's ONE clock read: `dt.now()` stamps "Date Prepared"
#: (legacy/gps_metadata_functions.py, §0 Form block). Every other date in the
#: log comes from TOS. Left un-scrubbed, every snapshot here would go red the
#: day after it was captured.
_DATE_PREPARED_RE = re.compile(
    r"^(?P<head>\s*Date Prepared\s*:\s*)(?P<date>\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)
_DATE_PREPARED_PLACEHOLDER = "<DATE-PREPARED>"

#: IGS v2.0 top-level sections. A log missing any of these is not a site log,
#: whatever it byte-compares equal to.
_REQUIRED_SECTIONS = (
    "0.   Form",
    "1.   Site Identification of the GNSS Monument",
    "2.   Site Location Information",
    "3.   GNSS Receiver Information",
    "4.   GNSS Antenna Information",
    "5.   Surveyed Local Ties",
    "6.   Frequency Standard",
    "7.   Collocation Information",
    "8.   Meteorological Instrumentation",
    "9.   Local Ongoing Conditions Possibly Affecting Computed Position",
    "10.  Local Episodic Effects Possibly Affecting Data Quality",
    "11.  On-Site, Point of Contact Agency Information",
    "12.  Responsible Agency (if different from 11.)",
    "13.  More Information",
)

#: A populated §3/§4 block is numbered (`3.1`, `4.2`); `3.x`/`4.x` is the
#: empty IGS template stub the renderer always emits last. Matching the stub
#: as if it were data is how a station that rendered NOTHING would look
#: fully populated.
#:
#: NOTE the trailing `(\S.*?)` requires a non-empty device model. The renderer
#: emits `device.get("model") or ""`, so a block for a device with no model in
#: TOS is invisible to these counts — and the contiguity check below would then
#: report a confusing `[1, 2, 4] != [1, 2, 3]`. None of the four fixture
#: stations has such a device. If a future fixture does, that gap is the
#: reason; fix it by capturing the number and model separately, not by
#: loosening the contiguity assertion.
_RECEIVER_BLOCK_RE = re.compile(r"^3\.(\d+)\s+Receiver Type\s*:\s*(\S.*?)\s*$", re.MULTILINE)
_ANTENNA_BLOCK_RE = re.compile(r"^4\.(\d+)\s+Antenna Type\s*:\s*(\S.*?)\s*$", re.MULTILINE)

#: TOS synthetic placeholder keys — `<subtype>-<STID>-<YYYYMMDD>`. None may
#: ever reach a published log; ISAK published one verbatim on 2026-08-04.
_SYNTHETIC_KEY_RE = re.compile(r"\b(?:antenna|gnss_receiver|monument|radome)-[A-Za-z]{4}-\d{8}\b")


def _scrub_volatile(log: str) -> str:
    """Replace the generation date so a snapshot survives the next day.

    Only the "Date Prepared" value is substituted; the surrounding column
    alignment is preserved, so a change to the §0 layout still shows up as a
    snapshot diff rather than being absorbed by the scrub.
    """
    return _DATE_PREPARED_RE.sub(
        lambda m: f"{m.group('head')}{_DATE_PREPARED_PLACEHOLDER}", log
    )


def _assert_publishable(log: str, station: str) -> None:
    """Structural floor, asserted BEFORE the byte-compare.

    A byte-comparison is satisfied by any two equal strings, including two
    equal *wrong* ones: if the renderer starts returning an error string, or
    a log whose §3/§4 collapsed to the bare IGS template, a snapshot captured
    from that same broken state compares equal and the oracle reports green
    while publishing garbage. These assertions are what a degenerate render
    cannot satisfy, so they must not be weakened into "log is non-empty".
    """
    assert log, f"{station}: renderer produced nothing — re-record the cassette"

    missing = [s for s in _REQUIRED_SECTIONS if s not in log]
    assert not missing, f"{station}: site log is missing IGS sections {missing}"

    receivers = _RECEIVER_BLOCK_RE.findall(log)
    assert receivers, (
        f"{station}: no NUMBERED §3 receiver block — only the '3.x' template "
        f"stub rendered, so the device-session chain produced nothing"
    )
    antennas = _ANTENNA_BLOCK_RE.findall(log)
    assert antennas, (
        f"{station}: no NUMBERED §4 antenna block — only the '4.x' template "
        f"stub rendered, so the device-session chain produced nothing"
    )

    # Blocks must be numbered 1..N contiguously; a gap means a session was
    # dropped between composition and rendering.
    for label, blocks in (("3", receivers), ("4", antennas)):
        numbers = [int(n) for n, _ in blocks]
        assert numbers == list(range(1, len(numbers) + 1)), (
            f"{station}: §{label} block numbering is {numbers}, expected "
            f"1..{len(numbers)} — a device session was dropped or reordered"
        )

    leaked = _SYNTHETIC_KEY_RE.findall(log)
    assert not leaked, (
        f"{station}: TOS synthetic placeholder key(s) {leaked} reached the "
        f"published log — this is the class of value M3G rejects with 422"
    )


@pytest.mark.vcr
@pytest.mark.parametrize("station", ORACLE_STATIONS)
def test_site_log_matches_snapshot(station: str) -> None:
    """``build_site_log(station)`` must byte-equal its committed snapshot.

    This is the F2 gate. The renderer is reached through the real production
    entry point, so the whole chain — station metadata fetch, device-session
    composition with the wide ``SITELOG_GPS_ATTRIBUTE_CODES``, agency
    resolution, and the legacy renderer itself — is under the lock.
    """
    log = build_site_log(station, loglevel=logging.CRITICAL)
    _assert_publishable(log, station)

    snapshot_path = SNAPSHOTS / f"{station}.log"
    actual = _scrub_volatile(log)

    if os.environ.get("SITELOG_ORACLE_UPDATE"):
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(actual, encoding="utf-8")
        pytest.skip(f"snapshot rewritten: {snapshot_path}")

    if not snapshot_path.exists():
        pytest.fail(
            f"Snapshot missing: {snapshot_path}\n"
            f"Capture it with:\n"
            f"  SITELOG_ORACLE_UPDATE=1 pytest tests/test_sitelog_oracle.py"
        )

    expected = snapshot_path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"{station}: rendered site log differs from its snapshot. This is a "
        f"change to a PUBLISHED artefact — review the diff, then re-snapshot "
        f"deliberately with SITELOG_ORACLE_UPDATE=1."
    )


@pytest.mark.vcr
def test_m3g_publish_shape_matches_snapshot() -> None:
    """The receivers/M3G argument shape, which the tests above do NOT cover.

    ``build_site_log(station)`` with defaults is the ``tosGPS sitelog`` path:
    ``previous_log=""`` (so ``report_type`` resolves to ``NEW``),
    ``modified_sections="1"``, ``monument_number="00"``, ``country_code="ISL"``,
    agencies auto-resolved. Receivers' publish call
    (``dissemination/sitelogs.py``) passes a *different* set — a real
    ``previous_log`` from ``find_previous_site_log`` (so ``UPDATE``), explicit
    ``monument_number``/``country_code``, and agencies resolved by the caller
    so an injected resolver is honoured.

    That difference is the reason ``build_site_log`` exists at all: the two
    publishers used to call the renderer directly with different arguments and
    agreed only because the omitted ones shared defaults. Locking one shape and
    calling the renderer covered would leave §0's dated-series chain
    ("Previous Site Log", "Modified/Added Sections") pinned at exactly one
    value — two of the regions F2 will edit.
    """
    from tostools.api.tos_client import TOSClient
    from tostools.core.agencies import resolve_sitelog_agencies

    client = TOSClient()
    meta = client.get_complete_station_metadata("RHOF")
    assert meta, "RHOF metadata empty — re-record the cassette"
    agencies = resolve_sitelog_agencies(client, meta)

    log = build_site_log(
        "RHOF",
        client=client,
        agencies=agencies,
        previous_log="rhof00isl_20250101.log",
        monument_number="00",
        country_code="ISL",
        loglevel=logging.CRITICAL,
    )
    _assert_publishable(log, "RHOF")

    # §0 must reflect the chained-series call, not the default NEW log.
    assert "rhof00isl_20250101.log" in log, "§0 lost the previous-log chain"
    report_types = re.findall(r"^\s*Report Type\s*:\s*(\S+)", log, re.MULTILINE)
    assert report_types == ["UPDATE"], (
        f"§0 Report Type is {report_types}, expected ['UPDATE'] — a non-empty "
        f"previous_log must flip the log out of NEW"
    )

    snapshot_path = SNAPSHOTS / "RHOF_m3g.log"
    actual = _scrub_volatile(log)
    if os.environ.get("SITELOG_ORACLE_UPDATE"):
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(actual, encoding="utf-8")
        pytest.skip(f"snapshot rewritten: {snapshot_path}")
    if not snapshot_path.exists():
        pytest.fail(
            f"Snapshot missing: {snapshot_path}\n"
            f"  SITELOG_ORACLE_UPDATE=1 pytest tests/test_sitelog_oracle.py"
        )
    assert actual == snapshot_path.read_text(encoding="utf-8"), (
        "the M3G publish shape's rendered log differs from its snapshot"
    )


@pytest.mark.vcr
def test_threaded_metadata_renders_identically_to_the_self_fetch() -> None:
    """Pre-fetched metadata must not change a single published byte.

    ``station``/``device_sessions`` (threaded through ``build_site_log`` by
    tostools ``93c432c``) exist so a caller that already holds the metadata —
    or a test — can render without touching TOS. Their entire contract is that
    they are a *transport* change, not a behaviour change.

    The failure this pins is specific and was called out when the seam was
    added: the obvious thing to thread in is
    ``client.get_complete_station_metadata``'s device sessions, but that client
    once composed with the NARROW attribute list while the renderer composes
    with the wide ``SITELOG_GPS_ATTRIBUTE_CODES``. Substituting one for the
    other drops §3 constellation sub-periods from a log published to M3G. Both
    now use the wide list, so this passes — and if anything ever re-narrows
    one of them, this is what goes red.
    """
    from tostools import gps_metadata_qc as gpsqc
    from tostools.api.tos_client import TOSClient
    from tostools.devices import SITELOG_GPS_ATTRIBUTE_CODES
    from tostools.devices import device_sessions as compose_device_sessions

    self_fetched = build_site_log("RHOF", loglevel=logging.CRITICAL)

    client = TOSClient(base_url=gpsqc.URL_REST_TOS)
    station, devices_history = gpsqc.get_station_metadata(
        "RHOF", gpsqc.URL_REST_TOS, loglevel=logging.CRITICAL
    )
    sessions = compose_device_sessions(
        client, devices_history, codes=SITELOG_GPS_ATTRIBUTE_CODES
    )
    assert sessions, "composed no device sessions — the fixture proves nothing"

    threaded = build_site_log(
        "RHOF",
        loglevel=logging.CRITICAL,
        station_metadata=station,
        device_sessions=sessions,
    )
    _assert_publishable(threaded, "RHOF")
    assert threaded == self_fetched, (
        "threading pre-fetched metadata changed the rendered site log; it is "
        "a transport seam and must be byte-neutral"
    )


@pytest.mark.vcr
def test_agency_resolution_did_not_silently_fall_back() -> None:
    """§11 must be the RESOLVED agency rendering, not the legacy fallback.

    ``build_site_log`` resolves §11/§12/§13 best-effort and, on any failure,
    falls back to the legacy TOS-contact rendering — logging a warning that
    every test here suppresses with ``loglevel=CRITICAL``. The two renderings
    genuinely differ (verified: the fallback comma-joins the mailing address
    onto one line; the resolved form emits IGS continuation rows), and §11 is
    the section M3G takes from the agency record.

    So without this, a snapshot could quietly capture the fallback and the
    oracle would lock a rendering production does not publish.
    """
    log = build_site_log("RHOF", loglevel=logging.CRITICAL)
    section = log.split("11.")[1].split("\n12.")[0]

    address_rows = re.findall(r"^\s*(?:Mailing Address\s*)?:\s*(\S.*)$", section, re.MULTILINE)
    assert "Bústaðarvegur 7-9, 105 Reykjavík, Iceland" not in section, (
        "§11 mailing address is comma-joined on one line — that is the legacy "
        "TOS-contact FALLBACK rendering, so agency resolution failed silently"
    )
    assert any("Bústaðarvegur" in row for row in address_rows), (
        f"§11 has no mailing address at all: {address_rows}"
    )


@pytest.mark.vcr
def test_date_prepared_is_stamped_with_today() -> None:
    """The one line the snapshot scrubs is covered here instead.

    Without this, ``_scrub_volatile`` would hide a renderer that stopped
    stamping the date, stamped a fixed date, or emitted a malformed one —
    the scrub would happily normalise all three into the same placeholder.
    """
    log = build_site_log("RHOF", loglevel=logging.CRITICAL)

    match = _DATE_PREPARED_RE.search(log)
    assert match, "§0 'Date Prepared' line is absent or malformed"
    assert match.group("date") == datetime.date.today().isoformat(), (
        f"§0 Date Prepared is {match.group('date')!r}, expected today's date"
    )
    assert _DATE_PREPARED_PLACEHOLDER not in log, (
        "the renderer emitted the test's own placeholder — the scrub would "
        "be indistinguishable from real output"
    )


@pytest.mark.vcr
def test_scrub_only_touches_the_generation_date() -> None:
    """``_scrub_volatile`` must not be a blanket date filter.

    Every other date in the log is TOS data under the byte-lock — install
    and removal dates especially. A scrub that widened to match those would
    silently stop guarding the era boundaries that ``rinex/corrector.py``
    writes into historical RINEX headers.
    """
    log = build_site_log("RHOF", loglevel=logging.CRITICAL)
    scrubbed = _scrub_volatile(log)

    assert scrubbed.count(_DATE_PREPARED_PLACEHOLDER) == 1, (
        "expected exactly one scrubbed line, got "
        f"{scrubbed.count(_DATE_PREPARED_PLACEHOLDER)}"
    )
    # The §3 install/removal dates are ISO-with-Z and must survive verbatim.
    installed = re.findall(r"Date Installed\s*:\s*(\d{4}-\d{2}-\d{2}T[\d:]+Z)", log)
    assert installed, "no §3 'Date Installed' values found — did §3 render?"
    for value in installed:
        assert value in scrubbed, f"scrub removed a TOS date: {value}"

    assert len(log.splitlines()) == len(scrubbed.splitlines()), (
        "scrub changed the line count — it must be a value substitution"
    )
