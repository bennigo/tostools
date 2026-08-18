"""A TOS placeholder antenna serial is never proposed as a header correction.

TOS assigns ``antenna-<STID>-<YYYYMMDD>`` when the real manufacturer serial is
unknown. That string is 21 characters; ``ANT # / TYPE`` gives the serial an A20
field. Writing it truncates to 20 and the serial runs straight into the antenna
type with no separating space::

    antenna-VMEY-2023011SEPCHOKE_B3E6   SPKE

65 VMEY files carry exactly that (measured 2026-08-18). Two independent paths
build a header antenna field from TOS — the converter
(``receivers.rinex.metadata_provider``) and this validator, which feeds
``--fix-headers``. Suppressing it in only one meant a ``--fix-headers`` run
proposed re-injecting the full 21-char serial the converter had just withheld,
i.e. the repair reproduced the damage.

The truncated form is also why these files flag at all: ``_norm_serial``
recognises a synthetic serial as "unknown" via ``-\\d{8}$``, and the truncated
value has only seven digits, so it compares as a real serial against TOS.
"""

from __future__ import annotations

from typing import Any, Dict

from tostools.rinex.validator import compare_rinex_to_tos

_SYNTHETIC = "antenna-VMEY-20230111"
_TRUNCATED = _SYNTHETIC[:20]  # what a previous write left in the header


def _rinex(serial: str, atype: str = "SEPCHOKE_B3E6", radome: str = "SPKE") -> Dict[str, str]:
    # A20 serial + A20 (16-char model + 4-char radome), as read off a header.
    return {"ANT # / TYPE": f"{serial.ljust(20)[:20]}{atype:<15} {radome:<4}"}


def _tos(serial: str, model: str = "SEPCHOKE_B3E6", radome: str = "SPKE") -> Dict[str, Any]:
    return {
        "antenna": {"serial_number": serial, "model": model},
        "radome": {"model": radome},
        "devices": {},
        "contact": {},
    }


def _correction(result) -> list | None:
    return result.get("corrections", {}).get("ANT # / TYPE")


class TestSyntheticSerialIsSuppressed:
    def test_correction_serial_is_empty_not_the_placeholder(self):
        # The whole point: repairing the truncated header must not write the
        # 21-char value back, which would truncate to the same damage again.
        out = compare_rinex_to_tos(_rinex(_TRUNCATED), _tos(_SYNTHETIC))
        assert _correction(out) is not None, "truncated serial must still flag"
        assert _correction(out)[0] == ""

    def test_type_and_radome_survive_the_suppression(self):
        # Blanking the serial must not blank the antenna identity with it.
        out = compare_rinex_to_tos(_rinex(_TRUNCATED), _tos(_SYNTHETIC))
        serial, atype, radome = _correction(out)
        assert (atype, radome) == ("SEPCHOKE_B3E6", "SPKE")
        assert serial == ""

    def test_the_repair_converges(self):
        # After the fix is written the header carries a blank serial; comparing
        # it again must report a match, or --fix-headers would rewrite the same
        # 65 files on every run.
        out = compare_rinex_to_tos(_rinex(""), _tos(_SYNTHETIC))
        assert _correction(out) is None
        assert "antenna" in out.get("matches", {})

    def test_a_well_formed_synthetic_serial_also_matches_a_blank_header(self):
        # _norm_serial already maps the untruncated form to None; this pins that
        # the suppression does not turn that agreement into a discrepancy.
        out = compare_rinex_to_tos(_rinex(""), _tos("antenna-RHOF-20180101"))
        assert _correction(out) is None


class TestRealSerialsAreUntouched:
    def test_a_real_serial_is_still_proposed(self):
        out = compare_rinex_to_tos(_rinex("000000"), _tos("1441045161"))
        assert _correction(out)[0] == "1441045161"

    def test_a_genuine_antenna_change_still_flags(self):
        # The DOY-186 case: a Trimble antenna in the header, SEPCHOKE in TOS.
        out = compare_rinex_to_tos(
            _rinex("262509", "TRM29659.00", "SCIS"), _tos(_SYNTHETIC)
        )
        serial, atype, radome = _correction(out)
        assert (atype, radome) == ("SEPCHOKE_B3E6", "SPKE")
        assert serial == ""

    def test_a_serial_shaped_like_a_placeholder_but_not_one_is_kept(self):
        # Only the three known subtypes with a four-char id and eight digits are
        # synthetic; a real serial must never be silently dropped.
        out = compare_rinex_to_tos(_rinex(""), _tos("antenna-part-1234"))
        assert _correction(out)[0] == "antenna-part-1234"
