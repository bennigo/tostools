"""ANT # / TYPE: emit on either part, and never truncate silently.

VMEY 2026-08-01 onwards carries 65 malformed headers:

    antenna-VMEY-2023011SEPCHOKE_B3E6   SPKE
                        ^ no separator

TOS's synthetic serial `antenna-VMEY-20230111` is 21 chars; the RINEX serial
field is A20. `ljust(20)[:20]` truncated it to exactly 20, consuming the whole
column, and said nothing. `reconstruct-from-archive` then read the truncated
string back, failed to match TOS's 21-char serial, and proposed CREATING A
DUPLICATE antenna — the dup-guard working correctly on corrupted input.
"""

import logging

from tostools.rinex.formatter import format_rinex_field


class TestEmitOnEitherPart:
    def test_blank_serial_still_emits_the_type(self):
        # The old `if not serial: return None` discarded the antenna type and
        # radome too — the fields downstream actually needs.
        out = format_rinex_field("ANT # / TYPE", ("", "SEPCHOKE_B3E6   SPKE"))
        assert out is not None
        assert "SEPCHOKE_B3E6" in out
        assert out.startswith(
            " " * 20
        ), "serial field must be blank-padded, not shifted"

    def test_both_blank_is_still_skipped(self):
        assert format_rinex_field("ANT # / TYPE", ("", "")) is None

    def test_real_serial_is_unchanged(self):
        out = format_rinex_field("ANT # / TYPE", ("1441045161", "TRM57971.00     NONE"))
        assert out == "1441045161          TRM57971.00     NONE"

    def test_column_alignment_is_preserved(self):
        # The type must start at column 20 whether or not a serial is present.
        with_sn = format_rinex_field("ANT # / TYPE", ("123", "TRM57971.00"))
        without = format_rinex_field("ANT # / TYPE", ("", "TRM57971.00"))
        assert with_sn[20:31] == "TRM57971.00"
        assert without[20:31] == "TRM57971.00"


class TestOverflowWarning:
    def test_oversized_serial_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            format_rinex_field(
                "ANT # / TYPE", ("antenna-VMEY-20230111", "SEPCHOKE_B3E6   SPKE")
            )
        assert any("21 chars" in r.getMessage() for r in caplog.records)

    def test_the_warning_shows_what_survives(self, caplog):
        with caplog.at_level(logging.WARNING):
            format_rinex_field("ANT # / TYPE", ("antenna-VMEY-20230111", "X"))
        text = " ".join(r.getMessage() for r in caplog.records)
        assert "antenna-VMEY-2023011" in text, "must show the truncated result"

    def test_a_fitting_serial_is_silent(self, caplog):
        with caplog.at_level(logging.WARNING):
            format_rinex_field("ANT # / TYPE", ("1441045161", "TRM57971.00"))
        assert not caplog.records

    def test_exactly_20_is_silent(self, caplog):
        with caplog.at_level(logging.WARNING):
            format_rinex_field("ANT # / TYPE", ("A" * 20, "TRM57971.00"))
        assert not caplog.records

    def test_truncation_still_happens(self):
        # The warning does not prevent it — the field width is fixed.
        out = format_rinex_field("ANT # / TYPE", ("antenna-VMEY-20230111", "X"))
        assert out[:20] == "antenna-VMEY-2023011"
