"""The RINEX ``REC # / TYPE / VERS`` comparator reads the right TOS field.

It read ``software_version``, which for Septentrio is the same quantity in a
different notation (``5.60`` against firmware ``5.6.0``). Measured on ISAK
2026-08-03: **200 of 202** daily files flagged "receiver mismatch" with headers
that were already correct. Acting on that via ``--fix-headers
--correct-receiver`` would have written ``5.60`` over 200 correct headers, on
every Septentrio station in the fleet.

Ground truth from TOS for four receiver families, all at ISAK:

    POLARX5        firmware '5.3.0'            software '5.30'
    NETR9          firmware '4.43'             software '4.43'
    TRIMBLE 5700   firmware 'NP 1.05 SP 0.00'  software '1.05'
    ASHTECH        firmware 'C00'              software '9.10'

The archived headers carry the firmware form in every case.
"""

from __future__ import annotations

from tostools.gps_rinex import receiver_version_for_header, versions_equivalent


class TestFieldPreference:
    def test_prefers_firmware_over_software(self):
        attrs = {"firmware_version": "5.3.0", "software_version": "5.30"}
        assert receiver_version_for_header(attrs) == "5.3.0"

    def test_falls_back_to_software_when_firmware_absent(self):
        assert receiver_version_for_header({"software_version": "4.60"}) == "4.60"

    def test_falls_back_when_firmware_is_none(self):
        attrs = {"firmware_version": None, "software_version": "4.60"}
        assert receiver_version_for_header(attrs) == "4.60"

    def test_missing_both_is_empty_not_none(self):
        """Downstream formats this into a fixed-width header field."""
        assert receiver_version_for_header({}) == ""

    def test_trimble_keeps_the_full_firmware_string(self):
        """'NP 1.05 SP 0.00' is what the header shows; '1.05' is the SwVer."""
        attrs = {"firmware_version": "NP 1.05 SP 0.00", "software_version": "1.05"}
        assert receiver_version_for_header(attrs) == "NP 1.05 SP 0.00"

    def test_ashtech_firmware_and_software_genuinely_differ(self):
        attrs = {"firmware_version": "C00", "software_version": "9.10"}
        assert receiver_version_for_header(attrs) == "C00"


class TestSeptentrioRegression:
    """The exact ISAK case: 200/202 files flagged on notation alone."""

    def test_correct_header_no_longer_mismatches(self):
        attrs = {"firmware_version": "5.6.0", "software_version": "5.60"}
        assert versions_equivalent("5.6.0", receiver_version_for_header(attrs))

    def test_a_genuinely_wrong_header_still_mismatches(self):
        attrs = {"firmware_version": "5.6.0", "software_version": "5.60"}
        assert not versions_equivalent("5.3.0", receiver_version_for_header(attrs))


class TestSeparatorTolerance:
    def test_trimble_slash_variant_matches(self):
        """TOS 'NP 1.05 SP 0.00' vs header 'NP 1.05 / SP 0.00' — punctuation."""
        assert versions_equivalent("NP 1.05 / SP 0.00", "NP 1.05 SP 0.00")

    def test_whitespace_runs_collapse(self):
        assert versions_equivalent("NP  1.05   SP 0.00", "NP 1.05 SP 0.00")

    def test_case_insensitive(self):
        assert versions_equivalent("np 1.05 sp 0.00", "NP 1.05 SP 0.00")

    def test_leading_trailing_space_ignored(self):
        assert versions_equivalent("  4.43  ", "4.43")

    def test_digits_must_still_match(self):
        """Normalisation must not paper over a real firmware difference."""
        assert not versions_equivalent("NP 1.04 / SP 0.00", "NP 1.05 SP 0.00")

    def test_minor_version_difference_still_flags(self):
        assert not versions_equivalent("4.43", "4.44")

    def test_none_tos_value_does_not_crash(self):
        assert not versions_equivalent("5.6.0", None)

    def test_both_empty_are_equivalent(self):
        assert versions_equivalent("", None)


class TestNetR9Unaffected:
    """Where the two TOS fields agree, behaviour is unchanged either way."""

    def test_identical_fields_still_match(self):
        attrs = {"firmware_version": "4.43", "software_version": "4.43"}
        assert versions_equivalent("4.43", receiver_version_for_header(attrs))
