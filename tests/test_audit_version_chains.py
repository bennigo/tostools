"""The audit that closes the loop on the software_version drift.

Nothing compared the two chains until this existed — `tos station verify`
reported clean while GAMIT SwVer published a value years stale. These pin
the comparison rules on synthetic chains, so they run offline and cover
shapes the live fleet no longer has (it was repaired 2026-08-22).
"""

from __future__ import annotations

import pytest

from tostools.audit_version_chains import (
    ChainDivergence,
    compare_chains,
    is_septentrio,
)


def _p(value, date_from, date_to=None):
    return {"value": value, "date_from": date_from, "date_to": date_to}


class TestIsSeptentrio:
    @pytest.mark.parametrize(
        "model", ["SEPT POLARX5", "sept polarx5", "SEPT ASTERX-M", "POLARX2"]
    )
    def test_septentrio_models(self, model):
        assert is_septentrio(model)

    @pytest.mark.parametrize("model", ["TRIMBLE NETR9", "LEICA GR10", "", None])
    def test_other_families_are_not(self, model):
        assert not is_septentrio(model)


class TestCompareChains:
    def test_a_mirrored_chain_is_clean(self):
        fw = [_p("5.1.2", "2017-07-12", "2019-10-16"), _p("5.6.0", "2019-10-16")]
        sw = [_p("5.12", "2017-07-12", "2019-10-16"), _p("5.60", "2019-10-16")]
        assert compare_chains(fw, sw) == []

    def test_the_VMEY_shape_never_chained(self):
        """One open software row against a multi-period firmware chain."""
        fw = [
            _p("5.1.2", "2017-07-11", "2019-10-15"),
            _p("5.3.0", "2019-10-15", "2023-07-02"),
            _p("5.5.0", "2023-07-02"),
        ]
        sw = [_p("5.1", "2017-07-11")]
        out = compare_chains(fw, sw)
        reasons = [d.reason for d in out]
        assert reasons.count("missing") == 2, "the two later periods are absent"
        assert "value" in reasons, "5.1 != 5.12 for the first period"

    def test_the_ISAK_shape_missing_the_newest_link(self):
        fw = [_p("5.6.0", "2026-02-16", "2026-08-01"), _p("5.7.0", "2026-08-01")]
        sw = [_p("5.60", "2026-02-16", "2026-08-01")]
        out = compare_chains(fw, sw)
        assert [d.reason for d in out] == ["missing"]
        assert out[0].expected == "5.70"

    def test_a_stale_value_with_correct_boundaries(self):
        fw = [_p("5.6.0", "2025-01-01")]
        sw = [_p("5.50", "2025-01-01")]
        out = compare_chains(fw, sw)
        assert [d.reason for d in out] == ["value"]
        assert (out[0].software, out[0].expected) == ("5.50", "5.60")

    def test_a_boundary_mismatch_is_its_own_reason(self):
        """Right value, wrong end date — a different repair from a wrong value."""
        fw = [_p("5.6.0", "2025-01-01", "2026-01-01")]
        sw = [_p("5.60", "2025-01-01", "2025-06-01")]
        assert [d.reason for d in compare_chains(fw, sw)] == ["boundary"]

    def test_the_SAUD_orphan(self):
        """A software period no firmware period starts at — the 2004 row."""
        fw = [_p("5.2.0", "2019-01-01")]
        sw = [_p("2.10", "2004-10-29")]
        out = compare_chains(fw, sw)
        reasons = sorted(d.reason for d in out)
        assert reasons[0] == "missing"
        assert "orphan" in reasons[1]

    def test_malformed_firmware_is_named_not_misblamed(self):
        """KEIC: firmware itself is '5.50'. Comparing values would be noise."""
        fw = [_p("5.50", "2023-09-28")]
        sw = [_p("5.50", "2023-09-28")]
        out = compare_chains(fw, sw)
        assert len(out) == 1
        assert "not a clean X.Y.Z" in out[0].reason
        assert out[0].expected is None

    def test_junk_software_is_a_value_divergence(self):
        for junk in ("-----", "xxx", "yyyy", "6.12"):
            out = compare_chains([_p("5.4.0", "2020-01-01")], [_p(junk, "2020-01-01")])
            assert [d.reason for d in out] == ["value"], junk

    def test_an_empty_software_chain_flags_every_period(self):
        fw = [_p("5.1.1", "2017-09-03", "2019-10-15"), _p("5.6.0", "2019-10-15")]
        out = compare_chains(fw, [])
        assert [d.reason for d in out] == ["missing", "missing"]


class TestDivergenceRendering:
    def test_describe_names_all_three_values(self):
        d = ChainDivergence("2020-01-01", None, "5.6.0", "5.50", "5.60", "value")
        text = d.describe()
        assert "5.6.0" in text and "5.50" in text and "5.60" in text
        assert "open" in text
