"""The config branch must not publish a TOS placeholder serial either.

``corrector.py`` builds ``ANT # / TYPE`` in two places: from a TOS session, and
from ``stations.cfg``. The TOS branch has always mapped a placeholder to
``0000``. The config branch wrote whatever cfg held — and ``cfg sync-from-tos``
mirrors ``antenna_serial`` FROM TOS, so TOS's synthetic placeholders reached
cfg and then the header.

At 21 characters ``antenna-thob-20200128`` does not fit the A20 field. It
truncated to ``antenna-thob-2020012``, filling the column exactly so the serial
abutted the antenna type with no separator:

    antenna-thob-2020012SEPCHOKE_B3E6   SPKE

Measured 2026-08-19: 26 stations carry a synthetic ``antenna_serial`` in
production ``stations.cfg``, 19 had a malformed header in their most recent
daily file, and a fresh conversion on rek-d01 still produced one. The earlier
fixes guarded ``metadata_provider`` (receivers) and ``validator`` (tostools) —
this path was never guarded, which is why the damage continued after both
shipped.
"""

import pytest

import logging

from tostools.rinex.corrector import _get_corrections_from_config


def _cfg(serial, ant_type="SEPCHOKE_B3E6", radome="SPKE"):
    return {
        "antenna": {"serial": serial, "type": ant_type, "radome": radome, "height": 0.999},
        "receiver": {},
        "rinex": {},
        "station": {},
    }


def _ant_field(corrections):
    return corrections.get("ANT # / TYPE")


class TestAPlaceholderNeverReachesTheHeader:
    @pytest.mark.parametrize(
        "serial",
        [
            "antenna-thob-20200128",  # THOB, live in stations.cfg today
            "antenna-VMEY-20230111",
            "antenna-thob-2020012",  # already truncated by a previous write
            "radome-REYK-20130502",
            "Unknown",
        ],
    )
    def test_it_is_replaced_with_0000(self, serial):
        field = _ant_field(_get_corrections_from_config("THOB", _cfg(serial), logging.getLogger("t")))
        assert field is not None
        assert field[0] == "0000"

    def test_a_real_serial_is_untouched(self):
        field = _ant_field(_get_corrections_from_config("THOB", _cfg("1441137916"), logging.getLogger("t")))
        assert field[0] == "1441137916"

    def test_the_antenna_type_survives_a_suppressed_serial(self):
        # Gating the whole field on the serial would drop TYPE and RADOME too —
        # a worse header than a blank serial.
        field = _ant_field(_get_corrections_from_config("THOB", _cfg("antenna-thob-20200128"), logging.getLogger("t")))
        assert "SEPCHOKE_B3E6" in field[1]
        assert "SPKE" in field[1]

    def test_no_serial_but_a_type_still_emits(self):
        field = _ant_field(_get_corrections_from_config("THOB", _cfg(""), logging.getLogger("t")))
        assert field is not None
        assert field[0] == "0000"
        assert "SEPCHOKE_B3E6" in field[1]

    def test_neither_serial_nor_type_emits_nothing(self):
        # Must not stamp a bare 0000 onto a station with no antenna configured.
        assert _ant_field(_get_corrections_from_config("THOB", _cfg("", ant_type=""), logging.getLogger("t"))) is None

    def test_the_written_field_fits_the_a20_column(self):
        # The failure was a width overflow, so assert the width directly.
        field = _ant_field(_get_corrections_from_config("THOB", _cfg("antenna-thob-20200128"), logging.getLogger("t")))
        assert len(field[0]) <= 20
