"""A TOS-internal synthetic serial must never reach a published site log.

``synthetic_serial()`` mints ``<subtype>-<STID>-<YYYYMMDD>`` because TOS requires
every device to carry a non-empty ``serial_number`` — radomes never have a
factory serial, antennas and steel monuments frequently do not either. It is a
lookup key (``move-device --serial`` matches on it), not equipment data.

The IGS site log is where that distinction bites: only the **first 5 characters**
of the serial field reach SINEX, so ELDC's ``antenna-eldc-20200129`` would be
distributed worldwide as ``anten``. The IGS instructions define no placeholder
for an unknown serial — the only guidance is "if an answer in an optional field
is unknown, try to learn the answer for the next log update" — so the correct
published value is an empty field.
"""

import pytest

from tostools.device import is_synthetic_serial, synthetic_serial


class TestIsSyntheticSerial:
    @pytest.mark.parametrize(
        "value",
        [
            "antenna-eldc-20200129",  # ELDC, as actually stored in TOS (lowercase)
            "radome-REYK-20130502",  # the form the docstring documents (uppercase)
            "monument-ABCD-19991231",
            " radome-eldc-20200129 ",  # surrounding whitespace
        ],
    )
    def test_recognises_sentinels(self, value):
        assert is_synthetic_serial(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "3068967",  # ELDC receiver, a real serial
            "1999040150",  # RHOF antenna, a real serial
            "1441045161",
            "000000",  # the legacy no-serial fallback, not a sentinel
            "",
            None,
            "antenna-eld-20200129",  # 3-char marker: not the pattern
            "SEPCHOKE-eldc-20200129",  # not one of the three subtypes
        ],
    )
    def test_leaves_everything_else_alone(self, value):
        assert is_synthetic_serial(value) is False

    @pytest.mark.parametrize(
        "value",
        [
            "antenna-VMEY-2023011",  # the 66 VMEY headers: A20 ate one digit
            "antenna-eldc-2020012",
            "monument-ABCD-199912",  # 22 chars -> A20 eats two
        ],
    )
    # The floor is 6 digits, the worst truncation the convention can produce
    # (monument-, 22 chars). Anything shorter would start claiming real serials
    # such as ``antenna-part-1234`` — asserted below.
    def test_recognises_a_field_truncated_sentinel(self, value):
        # Regression: this predicate used to demand exactly 8 digits, so a
        # placeholder truncated by RINEX's A20 ``ANT # / TYPE`` field read as a
        # REAL serial. That is how 66 VMEY headers defeated the reconstruct
        # dup-guard — the truncated value matched no TOS device, so the verb
        # proposed minting a duplicate antenna. Classifying a truncated
        # placeholder as real is the more expensive of the two errors.
        assert is_synthetic_serial(value) is True

    def test_agrees_with_the_minter(self):
        # If synthetic_serial's format ever changes, this catches the predicate
        # silently falling out of sync and letting sentinels through again.
        for subtype in ("antenna", "radome", "monument"):
            minted = synthetic_serial(subtype, "ELDC", "2020-01-29")
            assert is_synthetic_serial(minted), f"{minted!r} not recognised"

    def test_a_real_serial_that_merely_contains_a_hyphen_is_kept(self):
        # The match is anchored; a hyphenated real serial must survive.
        assert is_synthetic_serial("ANT-12345-XY") is False


class TestSiteLogRendering:
    """The two generators that render section 3/4 must both blank a sentinel.

    ``tosGPS sitelog`` renders through ``legacy.gps_metadata_functions.site_log``
    (tosGPS.py imports it as ``gpsf``), NOT through ``core.site_log`` — a fix
    applied only to the modern module has no effect on the published artefact.
    Both are patched; this pins that both import the predicate so a later
    refactor cannot quietly drop one.
    """

    def test_legacy_generator_imports_the_filter(self):
        import tostools.legacy.gps_metadata_functions as legacy

        assert hasattr(legacy, "is_synthetic_serial")

    def test_core_generator_imports_the_filter(self):
        import tostools.core.site_log as core

        assert hasattr(core, "is_synthetic_serial")
