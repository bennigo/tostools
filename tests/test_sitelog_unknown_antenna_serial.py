"""A suppressed antenna serial publishes as ``0000``, never as an empty field.

The synthetic ``<subtype>-<STID>-<YYYYMMDD>`` key must not be published — only
the first 5 characters reach SINEX, so ``antenna-eldc-20200129`` would be
distributed worldwide as ``anten``. The original fix blanked the field, on the
IGS instruction that an unknown optional answer is left empty.

**M3G refuses an empty antenna serial.** Established by bisecting VMEY's site
log against the live API on 2026-08-20, one variable at a time::

    M3G's own stored copy, verbatim         -> HTTP 200
    …with the antenna serial emptied        -> HTTP 422  'check the "Antenna" section'
    …with the radome changed NONE -> SCIS   -> HTTP 200
    our site log, blank serial              -> HTTP 422
    our site log, serial "0000"             -> HTTP 200

So the radome edit and the date corrections were never the problem; the empty
serial was, and only it. ``0000`` is non-empty for M3G, reads as ``0000`` in
SINEX rather than a misleading word fragment, and is already what both the RINEX
header convention and okada's GAMIT station.info carry for such an antenna.

Both generators are pinned. ``tosGPS sitelog`` renders through
``legacy.gps_metadata_functions``, NOT ``core.site_log``, so a fix applied to
only the modern module leaves the published artefact unchanged.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tostools.core.site_log import _generate_antenna_section
from tostools.device import PUBLISHED_UNKNOWN_ANTENNA_SERIAL


def _session(serial):
    return [
        {
            "time_from": datetime(2023, 1, 11),
            "time_to": None,
            "antenna": {
                "model": "SEPCHOKE_B3E6",
                "serial_number": serial,
                "antenna_height": 0.0,
                "antenna_reference_point": "BPA",
            },
        }
    ]


def _serial_line(text):
    for ln in text.splitlines():
        if "Serial Number" in ln and "Radome" not in ln:
            return ln.split(":", 1)[1].strip()
    return None


class TestTheConstant:
    def test_it_is_0000(self):
        # Empirically the value M3G accepts; see the module docstring.
        assert PUBLISHED_UNKNOWN_ANTENNA_SERIAL == "0000"

    def test_it_is_not_empty(self):
        # The whole point: an empty antenna serial is a 422 from M3G.
        assert PUBLISHED_UNKNOWN_ANTENNA_SERIAL.strip() != ""


class TestCoreGenerator:
    @pytest.mark.parametrize(
        "serial",
        [
            "antenna-VMEY-20230111",  # the VMEY case that produced the 422
            "antenna-eldc-20200129",  # lowercase, as stored on ELDC
            "antenna-VMEY-2023011",  # A20-truncated survivor
            "radome-REYK-20130502",
        ],
    )
    def test_a_synthetic_serial_renders_as_0000(self, serial):
        assert _serial_line(_generate_antenna_section(_session(serial))) == "0000"

    def test_a_real_serial_is_published_unchanged(self):
        assert _serial_line(_generate_antenna_section(_session("1441137916"))) == "1441137916"

    def test_the_synthetic_key_never_reaches_the_output(self):
        out = _generate_antenna_section(_session("antenna-VMEY-20230111"))
        assert "antenna-VMEY" not in out
        assert "anten " not in out  # the SINEX 5-char truncation


class TestBothGeneratorsAreFixed:
    def test_the_legacy_generator_imports_the_constant(self):
        # tosGPS sitelog publishes through THIS module. A fix applied only to
        # core/site_log.py would not change the published artefact at all.
        import tostools.legacy.gps_metadata_functions as legacy

        assert hasattr(legacy, "PUBLISHED_UNKNOWN_ANTENNA_SERIAL")

    def test_the_core_generator_imports_the_constant(self):
        import tostools.core.site_log as core

        assert hasattr(core, "PUBLISHED_UNKNOWN_ANTENNA_SERIAL")

    def test_neither_generator_still_blanks_an_antenna_serial(self):
        # Guards the regression directly: a refactor that restores `= ""` on the
        # antenna branch reintroduces the 422.
        import inspect

        import tostools.core.site_log as core

        src = inspect.getsource(core._generate_antenna_section)
        assert "PUBLISHED_UNKNOWN_ANTENNA_SERIAL" in src
        assert 'serial_num = ""' not in src
