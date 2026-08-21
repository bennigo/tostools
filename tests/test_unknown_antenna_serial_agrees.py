"""Every writer of an unknown antenna serial must emit the SAME value: "0000".

There were two "correct" answers for one field. `corrector.py` and `site_log.py`
normalised a suppressed serial to `PUBLISHED_UNKNOWN_ANTENNA_SERIAL` ("0000");
`validator.py` and receivers' `metadata_provider.py` normalised it to `""`,
citing the IGS instruction to leave an unknown optional field empty.

The IGS instruction is real, but M3G overrides it — an empty antenna Serial
Number is rejected with a 422, bisected against the live API on 2026-08-20:
M3G's own stored site log with the serial emptied returns 422; the identical log
carrying "0000" returns 200. `site_log.py` and `corrector.py` were moved then;
the other two were missed, which is why 463 archived 2026 daily files still
carried a blank serial field.

Disagreement here is not cosmetic. The validator's value is what `--fix-headers`
writes and the converter's value is what a fresh conversion writes; if they
differ, every freshly converted file reads back as discrepant and the repair
re-injects what the converter withheld.
"""

from __future__ import annotations

from tostools.device import PUBLISHED_UNKNOWN_ANTENNA_SERIAL, is_synthetic_serial

SYNTHETIC = "antenna-eldc-20200129"
TRUNCATED = "antenna-thob-2020012"  # what an A20 field leaves of one


class TestTheConstant:
    def test_is_the_m3g_accepted_value_not_empty(self):
        # "" is what M3G 422s on. The whole point of the constant.
        assert PUBLISHED_UNKNOWN_ANTENNA_SERIAL == "0000"
        assert PUBLISHED_UNKNOWN_ANTENNA_SERIAL != ""

    def test_it_survives_the_a20_rinex_field(self):
        # A stand-in that itself truncates would recreate the original bug.
        assert len(PUBLISHED_UNKNOWN_ANTENNA_SERIAL) <= 20

    def test_it_survives_the_sinex_5_char_truncation(self):
        # Only the first 5 chars of a serial reach SINEX — the reason a synthetic
        # serial must never be published ("antenna-eldc-…" would go out as "anten").
        assert PUBLISHED_UNKNOWN_ANTENNA_SERIAL[:5] == PUBLISHED_UNKNOWN_ANTENNA_SERIAL


class TestWritersAgree:
    """Each writer's suppression value, asserted at its own source of truth."""

    def test_validator_suppresses_to_the_constant(self):
        import inspect

        from tostools.rinex import validator

        src = inspect.getsource(validator.compare_rinex_to_tos)
        assert "_tos_serial = PUBLISHED_UNKNOWN_ANTENNA_SERIAL" in src, (
            "validator must publish the constant, not a blank — a blank is what "
            "M3G rejects and what disagrees with the converter"
        )

    def test_gps_rinex_writers_are_guarded(self):
        # These are the SECOND and THIRD writers of ANT # / TYPE, with their own
        # file-writing functions. The 2026-08-19 fleet bug was one guarded and one
        # unguarded builder of this exact field.
        import inspect

        from tostools import gps_rinex
        from tostools.legacy import gps_rinex as legacy_gps_rinex

        for mod in (gps_rinex, legacy_gps_rinex):
            src = inspect.getsource(mod)
            assert (
                "is_synthetic_serial(TOS_antenna_serial)" in src
            ), f"{mod.__name__} writes ANT # / TYPE unguarded"
            assert "PUBLISHED_UNKNOWN_ANTENNA_SERIAL" in src


class TestSuppressionStillTriggers:
    def test_a_synthetic_serial_is_recognised(self):
        assert is_synthetic_serial(SYNTHETIC)

    def test_a_truncated_synthetic_is_recognised(self):
        # The A20 survivor must still count — treating it as a real serial is how
        # 19 stations' damaged headers read back as "clean".
        assert is_synthetic_serial(TRUNCATED)

    def test_a_real_serial_is_not_suppressed(self):
        for real in ("5000113039", "12611789", "633Z024", "antenna-part-1234"):
            assert not is_synthetic_serial(real), f"{real} is a real serial"
