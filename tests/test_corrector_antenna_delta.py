"""ANTENNA: DELTA H/E/N is a composite on all three axes, on BOTH paths.

TOS splits the mark->ARP vector across two entities: the MONUMENT record holds
mark -> monument top, the ANTENNA record holds monument top -> ARP. The
published eccentricity is their sum. The IGS site log has always summed all
three axes (``legacy/gps_metadata_functions.py:196-204``); the RINEX header
path summed only UP and read EAST/NORTH off the antenna entity alone.

For every station whose offset happens to live on the antenna record the two
agreed by luck. For a station whose offset lives on the MONUMENT record they
did not, and nothing compared them:

    ISAK, 2026-08-04, archive file ISAK2160.26D.Z
        header   ANTENNA: DELTA H/E/N   1.0047   0.0000   0.0000
        site log Marker->ARP N Ecc.                       0.0002

    ISAK in TOS: antenna  E/N = 0.0    / 0.0
                 monument E/N = 0.0001 / 0.0002   <- never read

Of the 26 EPOS-disseminated stations, ISAK and AUST carry a non-zero monument
offset; the other 24 are zero on both entities, which is why this stayed
invisible. The disseminated (EPOS portal) copies take the TOS path with
``station_config=None`` and were affected by the E/N half of the same bug;
the archive copies took the config path, which additionally hardcoded the
eccentricity to zero and could never have carried it at all.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from tostools.rinex import corrector
from tostools.rinex.corrector import (
    _get_corrections_from_tos,
    _overlay_tos_antenna_delta,
    resolve_corrections,
)

_DELTA = "ANTENNA: DELTA H/E/N"

#: A config-path station: `config_valid_from` in the past, so an observation
#: date after it selects stations.cfg over TOS. `height` is the cfg composite.
_ISAK_CFG = {
    "rinex": {
        "config_valid_from": "2026-07-31",
        "marker_name": "ISAK",
        "marker_number": "10214M001",
        "observer": "GNSSatIMO",
        "agency": "Icelandic Meteorological Office",
    },
    "antenna": {
        "serial": "2505010005",
        "type": "SEPVC6150L",
        "radome": "SCIS",
        "height": 1.0047,
    },
    "receiver": {},
    "station": {},
}

_OBS_DATE = datetime(2026, 8, 4)


@pytest.fixture
def rinex_stub(tmp_path):
    """A minimal RINEX 3 header — enough for the position guard to read."""
    f = tmp_path / "ISAK2160.26o"
    f.write_text(
        "     3.04           OBSERVATION DATA    M (MIXED)           "
        "RINEX VERSION / TYPE\n"
        "ISAK                                                        "
        "MARKER NAME\n"
        "        1.0047        0.0000        0.0000                  "
        "ANTENNA: DELTA H/E/N\n"
        "  2627583.7328  -943252.7934  5715821.7375                  "
        "APPROX POSITION XYZ\n"
        "                                                            "
        "END OF HEADER\n"
    )
    return f


def _session(ant_e, ant_n, ant_h, mon_e, mon_n, mon_h):
    return {
        "time_from": "2020-01-01T00:00:00",
        "time_to": None,
        "antenna": {
            "model": "SEPVC6150L",
            "serial_number": "2505010005",
            "antenna_height": ant_h,
            "antenna_offset_east": ant_e,
            "antenna_offset_north": ant_n,
        },
        "monument": {
            "monument_height": mon_h,
            "monument_offset_east": mon_e,
            "monument_offset_north": mon_n,
        },
        "radome": {"model": "SCIS"},
        "gnss_receiver": {},
    }


@pytest.fixture
def fake_tos(monkeypatch):
    """Install a TOS payload; returns a setter so each test picks its geometry."""

    def _install(session, station="ISAK"):
        payload = {
            "device_history": [session],
            "lat": None,
            "lon": None,
            "altitude": None,
            "marker": station,
        }
        monkeypatch.setattr(
            corrector, "gps_metadata", lambda *a, **k: payload, raising=True
        )
        return payload

    return _install


class TestTheTosPathSumsAllThreeAxes:
    """The arithmetic itself: antenna + monument on H, E and N alike."""

    def test_east_and_north_add_the_monument_term(self, fake_tos):
        fake_tos(
            _session(
                ant_e=0.0,
                ant_n=0.0,
                ant_h=0.0,
                mon_e=0.0001,
                mon_n=0.0002,
                mon_h=1.0047,
            )
        )
        h, e, n = _get_corrections_from_tos("ISAK", _OBS_DATE, logging.CRITICAL)[_DELTA]
        assert (h, e, n) == pytest.approx((1.0047, 0.0001, 0.0002))

    def test_an_offset_on_either_entity_survives(self, fake_tos):
        """The split is a data-entry choice; both spellings must reach the header."""
        fake_tos(
            _session(
                ant_e=0.03,
                ant_n=-0.02,
                ant_h=0.15,
                mon_e=0.0001,
                mon_n=0.0002,
                mon_h=1.0,
            )
        )
        h, e, n = _get_corrections_from_tos("ISAK", _OBS_DATE, logging.CRITICAL)[_DELTA]
        assert (h, e, n) == pytest.approx((1.15, 0.0301, -0.0198))

    def test_a_genuinely_zero_eccentricity_stays_zero(self, fake_tos):
        """The 24 EPOS stations with no offset anywhere must not acquire one."""
        fake_tos(
            _session(ant_e=0.0, ant_n=0.0, ant_h=0.0, mon_e=0.0, mon_n=0.0, mon_h=0.107)
        )
        h, e, n = _get_corrections_from_tos("ISAK", _OBS_DATE, logging.CRITICAL)[_DELTA]
        assert (h, e, n) == pytest.approx((0.107, 0.0, 0.0))


class TestTheConfigPathPublishesTheEccentricity:
    """The dispatcher must re-source the triple even when stations.cfg wins.

    Asserted through resolve_corrections(), not the config builder, because the
    config builder is *supposed* to keep emitting a zeroed placeholder — testing
    it directly would pass against the unfixed code.
    """

    def test_config_is_genuinely_the_selected_path(self, rinex_stub, fake_tos, caplog):
        fake_tos(_session(0.0, 0.0, 0.0, 0.0001, 0.0002, 1.0047))
        with caplog.at_level(logging.DEBUG, logger="tostools.rinex.corrector"):
            resolve_corrections(
                rinex_stub,
                "ISAK",
                _OBS_DATE,
                station_config=_ISAK_CFG,
                loglevel=logging.DEBUG,
            )
        assert "Using station.cfg for ISAK" in caplog.text, (
            "the config branch was not taken — this test would then prove "
            "nothing about the config path"
        )

    def test_the_monument_eccentricity_reaches_the_header(self, rinex_stub, fake_tos):
        fake_tos(_session(0.0, 0.0, 0.0, 0.0001, 0.0002, 1.0047))
        got = resolve_corrections(
            rinex_stub,
            "ISAK",
            _OBS_DATE,
            station_config=_ISAK_CFG,
            loglevel=logging.CRITICAL,
        )[_DELTA]
        assert got == pytest.approx((1.0047, 0.0001, 0.0002)), (
            "the config path published a zeroed eccentricity — stations.cfg has "
            "no E/N fields, so this triple must come from TOS"
        )

    def test_config_still_owns_the_descriptive_fields(self, rinex_stub, fake_tos):
        """Only geometry moves. Marker/observer/agency stay config-owned."""
        fake_tos(_session(0.0, 0.0, 0.0, 0.0001, 0.0002, 1.0047))
        got = resolve_corrections(
            rinex_stub,
            "ISAK",
            _OBS_DATE,
            station_config=_ISAK_CFG,
            loglevel=logging.CRITICAL,
        )
        assert got["MARKER NAME"] == ["ISAK"]
        assert got["OBSERVER / AGENCY"] == [
            "GNSSatIMO",
            "Icelandic Meteorological Office",
        ]


class TestAnUnreachableTosDoesNotBreakDailyConversion:
    """The config path exists so a daily run does not hard-depend on TOS."""

    @pytest.mark.parametrize(
        "boom",
        [
            pytest.param(SystemExit(1), id="sys.exit-on-connection-error"),
            pytest.param(OSError("dns"), id="transport-error"),
        ],
    )
    def test_the_config_value_survives_a_tos_failure(self, boom, monkeypatch, caplog):
        def _raise(*a, **k):
            raise boom

        monkeypatch.setattr(corrector, "gps_metadata", _raise, raising=True)
        kept = _overlay_tos_antenna_delta(
            {_DELTA: [1.0047, 0.0, 0.0]},
            "ISAK",
            _OBS_DATE,
            logging.CRITICAL,
            logging.getLogger("tostools.rinex.corrector"),
        )
        assert kept[_DELTA] == [1.0047, 0.0, 0.0], (
            "an unreachable TOS must leave the cfg value in place, not blank "
            "the header and not abort the run"
        )

    def test_an_empty_tos_answer_keeps_the_config_value(self, monkeypatch):
        monkeypatch.setattr(corrector, "gps_metadata", lambda *a, **k: {}, raising=True)
        kept = _overlay_tos_antenna_delta(
            {_DELTA: [1.0047, 0.0, 0.0]},
            "ISAK",
            _OBS_DATE,
            logging.CRITICAL,
            logging.getLogger("tostools.rinex.corrector"),
        )
        assert kept[_DELTA] == [1.0047, 0.0, 0.0]


@pytest.mark.vcr
def test_isaks_real_tos_record_pins_the_published_eccentricity(rinex_stub):
    """The canary, against a recorded TOS payload rather than a hand-built one.

    The fakes above pin the ARITHMETIC; this pins the FIELD NAMES and the shape
    of a real TOS answer. A rename of ``monument_offset_north`` upstream, or a
    session resolver that stops reaching the monument entity, breaks here and
    nowhere else — both fakes would happily keep passing.

    0.0002 is the value ISAK's IGS site log has always published while its RINEX
    headers read 0.0000. Re-record only if TOS's ISAK geometry genuinely changes:
        pytest tests/test_corrector_antenna_delta.py --record-mode=rewrite
    """
    got = resolve_corrections(
        rinex_stub,
        "ISAK",
        _OBS_DATE,
        station_config=_ISAK_CFG,
        loglevel=logging.CRITICAL,
    )[_DELTA]
    h, e, n = got
    assert (e, n) == pytest.approx((0.0001, 0.0002)), (
        f"config-path header published E/N {(e, n)} for ISAK; TOS's monument "
        "record carries 0.0001/0.0002 and the site log publishes it"
    )
    assert h == pytest.approx(1.0047), "the UP composite regressed"
