"""F1 step 2: the site-log attribute list has one definition.

`device_attribute_history` exists twice — top-level and under `legacy/` — and
the two copies carried DIFFERENT hardcoded `key_list`s: the legacy one fetched
the GNSS constellation toggles (GAL/BDS/QZSS/SBAS/IRN) and `azimuth`, the
top-level one stopped at GPS/GLO. A third copy of the same list lived in
`devices.SITELOG_GPS_ATTRIBUTE_CODES`, whose comment said it mirrored the legacy
one. See `docs/architecture/legacy-fork-unification-plan.md`.

That mattered because this chain feeds every published site log:

    core/site_log.py:127 -> get_complete_station_metadata
      -> get_device_sessions -> _get_device_attribute_history
        -> device_attribute_history

so the short list reaching it would drop §3.3 Satellite System back to the
"GPS" fleet-baseline fallback and §4 Alignment from True N to 0.0 — a loss that
reads as a TOS metadata gap rather than a code change, and would therefore be
chased on the wrong side for a long time.

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

import pytest

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


class TestSiteLogKeepsConstellationsAndAzimuth:
    """The regression this whole ordering exists to prevent.

    Mutation-tested: restoring the narrow hardcoded `key_list` on the top-level
    copy turns both of these red.
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

    def test_no_hardcoded_key_list_remains_in_either_copy(self):
        """Belt and braces: the divergence was two hardcoded lists, so assert
        neither module rebuilt one."""
        import pathlib

        import tostools.gps_metadata_qc as current
        import tostools.legacy.gps_metadata_qc as legacy

        for mod in (current, legacy):
            src = pathlib.Path(mod.__file__).read_text()
            assert (
                "SITELOG_GPS_ATTRIBUTE_CODES" in src
            ), f"{mod.__name__} no longer reads the shared constant"
            assert (
                '"QZSS",' not in src
            ), f"{mod.__name__} appears to have re-hardcoded an attribute list"


class TestTheTwoCopiesStillAgree:
    """Transitional guard — delete with `legacy/gps_metadata_qc.py` in F1 step 4.

    Same method that made step 1 safe: while both copies exist, an edit to one
    is a divergence, and it should fail here rather than in a published log
    months later.
    """

    @pytest.mark.parametrize("session_end", [None, "2026-01-01T00:00:00"])
    @pytest.mark.parametrize("device", [_receiver, _antenna], ids=["receiver", "ant"])
    def test_identical_output(self, device, session_end):
        legacy_mod = pytest.importorskip("tostools.legacy.gps_metadata_qc")
        from tostools.gps_metadata_qc import device_attribute_history as modern

        assert modern(device(), FROM, session_end, logging.CRITICAL) == (
            legacy_mod.device_attribute_history(
                device(), FROM, session_end, logging.CRITICAL
            )
        )
