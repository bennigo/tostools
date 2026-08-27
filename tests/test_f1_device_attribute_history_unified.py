"""F1 step 2: the site-log attribute list has one definition.

`device_attribute_history` exists twice — top-level and under `legacy/` — and
the two copies carried DIFFERENT hardcoded `key_list`s: the legacy one fetched
the GNSS constellation toggles (GAL/BDS/QZSS/SBAS/IRN) and `azimuth`, the
top-level one stopped at GPS/GLO. A third copy of the same list lived in
`devices.SITELOG_GPS_ATTRIBUTE_CODES`, whose comment said it mirrored the legacy
one. See `docs/architecture/legacy-fork-unification-plan.md`.

That mattered because of this chain:

    core/site_log.py:127 -> get_complete_station_metadata
      -> get_device_sessions -> _get_device_attribute_history
        -> device_attribute_history

**Where that chain actually goes, verified rather than inherited from the plan:**
it feeds §11/§12/§13 agency resolution, `_build_history_from_connections`, and
every receivers consumer of `get_complete_station_metadata` (`cfg reconcile`,
`tos_adapter`, `tos_push`, `stream_scheduler`, `skeleton`, dissemination
metadata). It does **not** feed §3.3/§4 of a published site log: no production
caller passes `device_sessions=`, so `site_log` composes its own via
`devices.device_sessions` — a different kernel that never calls this function.
The plan says a naive repoint would have dropped §3.3/§4 "out of every published
site log"; that was overstated. The real exposure was the station-metadata dicts
receivers reads, where a dropped attribute is equally invisible.

Step 2 collapses the list onto the shared constant and makes the
site-log-complete set the DEFAULT, so a caller cannot lose §3.3/§4 by failing to
ask for them. `TestSiteLogKeepsConstellationsAndAzimuth` is the guard that has
to survive: it goes red if the narrow key list is ever restored.

Deliberately NOT tested here: a constellation toggle that changes mid-tenure.
`coalesce_render_sessions` and `absorb_short_boundary_sessions` are live on this
path (the ISAK one-day-sliver logic), and a merge there could mask or manufacture
the result. The fixture keeps one constant-constellation tenure so a failure can
only mean the attribute was dropped.
"""

from __future__ import annotations

import logging

from tostools.devices import LEGACY_GPS_ATTRIBUTE_CODES, SITELOG_GPS_ATTRIBUTE_CODES

FROM = "2020-01-01T00:00:00"


def _attr(code, value, date_from=FROM, date_to=None):
    return {"code": code, "value": value, "date_from": date_from, "date_to": date_to}


def _receiver():
    """A PolaRx5 tracking GPS+GLO+GAL for its whole tenure."""
    return {
        "id_entity": 1001,
        "code_entity_subtype": "gnss_receiver",
        "attributes": [
            _attr("serial_number", "3018434"),
            _attr("model", "SEPT POLARX5"),
            _attr("firmware_version", "5.7.0"),
            _attr("GPS", "true"),
            _attr("GLO", "true"),
            _attr("GAL", "true"),
            # An attribute outside the key list — must be ignored, not carried.
            _attr("owner", "Jarðeðlismælihópur"),
        ],
    }


def _antenna():
    """An antenna with a non-zero azimuth — §4 Alignment from True N."""
    return {
        "id_entity": 2002,
        "code_entity_subtype": "antenna",
        "attributes": [
            _attr("serial_number", "CR62001234"),
            _attr("model", "LEIAR25.R4"),
            _attr("antenna_reference_point", "BAM"),
            _attr("antenna_height", "0.0500"),
            _attr("azimuth", "45"),
        ],
    }


STATION = {
    "name": "Prófstöð",
    "marker": "TEST",
    "iers_domes_number": "12345M001",
    "lat": 64.13,
    "lon": -21.94,
    "altitude": 78.8,
    "date_start": "2020-01-01 00:00",
    "geological_characteristic": "bedrock",
    "bedrock_type": "igneous",
    "is_near_fault_zones": "NEI",
    "country": "Ísland",
    "tectonic_plate": "EURASIAN",
}

# Injected so the renderer takes the agencies path instead of TOS contacts —
# §11/§12/§13 are not what this test is about, and the TOS path needs a client.
AGENCIES = {
    "poc": {
        "name_lines": ["Icelandic Meteorological Office"],
        "abbrev": "IMO",
        "address": ["Bústaðarvegur 7-9", "105 Reykjavík"],
        "contact_name": "GNSS Operator",
        "phone": "+354 5226000",
        "email": "gnss-epos@vedur.is",
    },
    "responsible": {
        "name_lines": ["Icelandic Meteorological Office"],
        "abbrev": "IMO",
        "address": [],
        "contact_name": "",
        "phone": "",
        "email": "",
    },
    "data_center": {"primary": "IMO", "secondary": "", "url": "https://en.vedur.is"},
}


def _sessions():
    """Drive the REAL chain: TOS attribute rows -> get_device_sessions.

    The renderer also accepts `device_sessions=` built by hand — but that seam
    bypasses `device_attribute_history` entirely, so a fixture built that way
    would pass identically with the narrow key list restored and would guard
    nothing. Only `_make_request` is stubbed; everything below it is production
    code.
    """
    from tostools.api.tos_client import TOSClient

    devices = {1001: _receiver(), 2002: _antenna()}
    client = TOSClient(loglevel=logging.CRITICAL)
    client._make_request = lambda endpoint, **kw: devices.get(
        int(endpoint.strip("/").split("/")[-1])
    )
    history = {
        "children_connections": [
            {"id_entity_child": 1001, "time_from": FROM, "time_to": None},
            {"id_entity_child": 2002, "time_from": FROM, "time_to": None},
        ]
    }
    return client.get_device_sessions(history)


def _render():
    from tostools.legacy.gps_metadata_functions import site_log

    return site_log(
        "TEST",
        loglevel=logging.CRITICAL,
        station=dict(STATION),
        device_sessions=_sessions(),
        agencies=AGENCIES,
    )


def _subsection(log: str, label: str) -> list[str]:
    """Return the lines of one rendered subsection, e.g. "3.1" or "4.1".

    Assertions must never run against the whole log: every section ends with a
    "3.x"/"4.x" INSTRUCTION block, and §3.x's placeholder text is literally
    "(GPS+GLO+GAL+BDS+QZSS+IRNSS+SBAS)" — so `"GPS+GLO+GAL" in log` is true even
    when the real subsection has fallen back to a bare "GPS".
    """
    lines = log.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"{label:<5}"))
    end = next(
        (i for i in range(start + 1, len(lines)) if not lines[i].strip()), len(lines)
    )
    return lines[start:end]


def _field(section: list[str], name: str) -> str:
    for line in section:
        head, _, value = line.partition(":")
        if head.strip().endswith(name) or head.strip() == name:
            return value.strip()
    raise AssertionError(f"field {name!r} not found in:\n" + "\n".join(section))


class TestDeviceSessionsKeepConstellationsAndAzimuth:
    """The contract of the repointed chain, asserted where production reads it.

    `get_device_sessions` is the seam every consumer of
    `get_complete_station_metadata` sits behind — receivers' `cfg reconcile`,
    `tos_adapter`, `stream_scheduler`, `skeleton`, and the dissemination
    metadata lookups. If the narrow key list comes back, these session dicts
    lose the constellations and `azimuth` silently.

    Mutation-tested: restoring the narrow `key_list` on whichever copy is live
    turns these red.
    """

    def test_receiver_session_carries_every_tracked_constellation(self):
        receiver = next(
            s["device"]
            for s in _sessions()
            if s["device"]["code_entity_subtype"] == "gnss_receiver"
        )
        assert receiver["GAL"] == "true"
        assert receiver["GPS"] == receiver["GLO"] == "true"
        # Present-but-unset, not absent — absent is what the narrow list gave.
        for code in ("BDS", "QZSS", "SBAS", "IRN"):
            assert code in receiver

    def test_antenna_session_carries_azimuth(self):
        antenna = next(
            s["device"]
            for s in _sessions()
            if s["device"]["code_entity_subtype"] == "antenna"
        )
        assert antenna["azimuth"] == "45"


class TestSiteLogKeepsConstellationsAndAzimuth:
    """§3.3 / §4 survive when sessions from this chain are handed to the renderer.

    Scope, stated precisely because the plan overstated it and this test was
    written to that overstatement: `site_log(device_sessions=...)` is a real
    public entry point, but **no production caller passes it**. `build_site_log`
    never does, so `site_log` builds its own sessions internally via
    `devices.device_sessions(codes=SITELOG_GPS_ATTRIBUTE_CODES)` — a different
    kernel (`slice_attributes_by_window`), which never reaches
    `device_attribute_history`.

    So this class does NOT guard §3.3/§4 of published logs; those were never at
    risk from the F1 repoint. What it does guard is that the two session
    producers stay interchangeable at the renderer's input — which is what makes
    the injection API safe to use and would be the first thing to break if the
    kernels diverge again. `TestDeviceSessionsKeepConstellationsAndAzimuth`
    above is the guard on the production path.
    """

    def test_satellite_system_renders_all_tracked_constellations(self):
        section = _subsection(_render(), "3.1")
        assert _field(section, "Satellite System") == "GPS+GLO+GAL"

    def test_satellite_system_is_not_the_bare_gps_fallback(self):
        """State the failure mode explicitly.

        `satellite_system_from_toggles` falls back to "GPS" when no toggle is
        set 'true' — which is exactly what a dropped GAL/BDS/... attribute looks
        like downstream. Indistinguishable from a GPS-only receiver by eye.
        """
        section = _subsection(_render(), "3.1")
        assert _field(section, "Satellite System") != "GPS"

    def test_alignment_from_true_n_renders_the_recorded_azimuth(self):
        section = _subsection(_render(), "4.1")
        assert _field(section, "Alignment from True N") == "45.0"

    def test_alignment_is_not_the_zero_default(self):
        """A dropped `azimuth` renders 0.0, which reads as "aligned to north"
        rather than as missing data."""
        section = _subsection(_render(), "4.1")
        assert _field(section, "Alignment from True N") not in ("0.0", "0.0000")


class TestOneDefinitionFeedsEveryCaller:
    def test_default_codes_are_the_sitelog_set(self):
        """The site-log-complete list is the DEFAULT, not something a caller
        has to know to ask for — that knowledge is what got lost the first
        time."""
        from tostools.gps_metadata_qc import device_attribute_history

        rows = device_attribute_history(_receiver(), FROM, None, logging.CRITICAL)
        assert rows
        for code in SITELOG_GPS_ATTRIBUTE_CODES:
            assert code in rows[0], f"{code} missing from the synthesised session"

    def test_widening_the_codes_moves_period_boundaries_not_just_keys(self):
        """`codes` is not only a filter — it decides which attribute rows are
        seen at all (`if item["code"] in key_list`), and a row that enters the
        loop can move `date_from`/`date_to`. Widening the default therefore
        changes PERIODS, not merely the keys on existing ones.

        Pinned because the collapse commit claimed the deprecated
        `--use-legacy-synthesis` chain's sub-session splits "can get finer"
        without having verified the shape. Measured here, the effect on a
        single-period device is sharper and in the other direction: a GAL toggle
        starting mid-tenure moves the session's `date_from` onto the toggle date
        and the pre-GAL period disappears rather than splitting off.

        That is this kernel's documented Bug 1 — `set(zip(dates_from, dates_to))`
        dedup collapsing a misaligned sub-window
        (docs/architecture/synthesis-legacy-divergence.md). It is NOT introduced
        by F1: the legacy copy always carried the wide list, so the tos_client
        path has always behaved this way, and it is exactly why the site-log
        renderer composes sessions with `devices.slice_attributes_by_window`
        instead. Asserted so the property is stated as a measured fact rather
        than assumed away, and so a future fix to Bug 1 fails here loudly.
        """
        from tostools.gps_metadata_qc import device_attribute_history

        # Built inline, not from `_receiver()`: GAL must be enabled ONLY from
        # 2022 — appending to the shared fixture would leave two concurrently
        # OPEN GAL periods, which TOS cannot hold, and the measurement would
        # then be of malformed input.
        dev = {
            "id_entity": 1001,
            "code_entity_subtype": "gnss_receiver",
            "attributes": [
                _attr("serial_number", "3018434"),
                _attr("model", "SEPT POLARX5"),
                _attr("firmware_version", "5.7.0"),
                _attr("GPS", "true"),
                _attr("GLO", "true"),
                # The toggle that shares a boundary with nothing else.
                _attr("GAL", "true", "2022-03-07T00:00:00"),
            ],
        }

        narrow = device_attribute_history(
            dev, FROM, None, logging.CRITICAL, codes=LEGACY_GPS_ATTRIBUTE_CODES
        )
        wide = device_attribute_history(dev, FROM, None, logging.CRITICAL)

        assert [(r["date_from"], r["date_to"]) for r in narrow] == [(FROM, None)]
        assert [(r["date_from"], r["date_to"]) for r in wide] == [
            ("2022-03-07T00:00:00", None)
        ]

    def test_narrow_list_is_still_reachable_explicitly(self):
        """`codes=` keeps the historical key list available — the slicer oracle
        in test_devices.py depends on it."""
        from tostools.gps_metadata_qc import device_attribute_history

        rows = device_attribute_history(
            _receiver(), FROM, None, logging.CRITICAL, codes=LEGACY_GPS_ATTRIBUTE_CODES
        )
        assert rows
        assert "GAL" not in rows[0]
        assert "serial_number" in rows[0]

    def test_no_hardcoded_key_list_remains(self):
        """Belt and braces: the divergence was two hardcoded lists, so assert
        the surviving module has not rebuilt one.

        Checked both copies until `legacy/gps_metadata_qc.py` was deleted in
        F1 step 4; one copy is the point of that deletion.

        The literal checked is `"serial_number",` — the first element of BOTH
        the wide and the narrow list. An earlier version of this test looked for
        `"QZSS",`, which the narrow list never contained: it would have passed
        through the exact regression it claimed to catch.
        """
        import pathlib

        import tostools.gps_metadata_qc as current

        for mod in (current,):
            src = pathlib.Path(mod.__file__).read_text()
            assert (
                "SITELOG_GPS_ATTRIBUTE_CODES" in src
            ), f"{mod.__name__} no longer reads the shared constant"
            assert (
                '"serial_number",' not in src
            ), f"{mod.__name__} appears to have re-hardcoded an attribute list"
