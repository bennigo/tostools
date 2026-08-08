"""A large APPROX POSITION delta must never be "corrected" away.

`compare_rinex_to_tos` emits a correction that rewrites APPROX POSITION XYZ to
the TOS surveyed position whenever the header is beyond the coordinate
tolerance. That is right for an a-priori position wrong by metres, and
catastrophic for one wrong by kilometres: the file was recorded somewhere else,
and rewriting the position launders it into looking authentic under this
station's marker, coordinates and DOMES.

Measured on ISAK: its receiver was taken off the mark for a campaign survey in
August 2016 (5 marks, up to 220 km away). The correction moved all 14 days onto
ISAK's position; the dissemination QC gate then compared the REWRITTEN header
against TOS, found it matching, and published every one to the EPOS portal.
"""

from __future__ import annotations

from tostools.rinex.validator import (
    _MAX_POSITION_CORRECTION_M,
    compare_rinex_to_tos,
)

# ISAK's surveyed position, and the campaign mark 220 km north its receiver
# actually occupied on days 214-217 of 2016.
ISAK_SESSION = {
    "marker": "ISAK",
    "lat": 64.119329,
    "lon": -19.747178,
    "altitude": 319.479303,
}
ISAK_XYZ = "  2627583.4397  -943252.7548  5715821.3894"
CAMPAIGN_XYZ = "  2475668.5588  -773840.8653  5807475.5828"


def _compare(xyz):
    return compare_rinex_to_tos(
        {"rinex file": "ISAK2140.16D.Z", "APPROX POSITION XYZ": xyz},
        dict(ISAK_SESSION),
    )


class TestFarPositionIsRefused:
    def test_the_isak_campaign_case_gets_no_correction(self):
        """The exact file that was published 220 km from where it was recorded."""
        r = _compare(CAMPAIGN_XYZ)
        assert "APPROX POSITION XYZ" not in r.get("corrections", {})

    def test_the_discrepancy_is_kept_so_a_gate_can_block(self):
        """Refusing the correction must not also hide the problem."""
        r = _compare(CAMPAIGN_XYZ)
        assert "coordinates" in r["discrepancies"]

    def test_the_refusal_is_explained(self):
        r = _compare(CAMPAIGN_XYZ)
        assert "refused_correction" in r["discrepancies"]["coordinates"]

    def test_the_distance_is_reported(self):
        r = _compare(CAMPAIGN_XYZ)
        d = r["discrepancies"]["coordinates"]["distance_m"]
        assert d > 200_000  # hundreds of km, not a header typo


class TestNearPositionIsStillCorrected:
    def test_a_matching_position_is_a_match(self):
        r = _compare(ISAK_XYZ)
        assert "coordinates" in r.get("matches", {})
        assert "coordinates" not in r["discrepancies"]

    def test_a_metre_scale_error_is_still_corrected(self):
        """The legitimate use — a stale or hand-entered a-priori position."""
        x, y, z = (float(v) for v in ISAK_XYZ.split())
        r = _compare(f"  {x + 50:.4f}  {y:.4f}  {z:.4f}")
        assert "APPROX POSITION XYZ" in r["corrections"]
        assert "refused_correction" not in r["discrepancies"]["coordinates"]

    def test_the_bound_sits_between_the_two_regimes(self):
        """Far above any real a-priori error, far below any wrong-site distance."""
        assert 100.0 < _MAX_POSITION_CORRECTION_M < 10_000.0


class TestCorrectorRefusesTheRewrite:
    """The corrector is the path that actually launders the file.

    `compare_rinex_to_tos` is the QC/compare path; `corrector` is the one
    `set_header` uses, and it builds its own corrections without consulting the
    validator. Guarding only the validator left the laundering intact — verified
    in production, where the campaign file still pushed after that fix.
    """

    def _corrections(self, tmp_path, header_xyz, tos_xyz):
        from unittest.mock import patch

        from tostools.rinex import corrector

        f = tmp_path / "ISAK2140.16D"
        f.write_text("dummy")
        corr = {"APPROX POSITION XYZ": list(tos_xyz), "MARKER NAME": ["ISAK"]}
        with patch.object(corrector, "read_rinex_header", return_value={"header": []}):
            with patch(
                "tostools.rinex.reader.extract_header_info",
                return_value={"APPROX POSITION XYZ": header_xyz},
            ):
                return corrector._guard_position_correction(
                    f, corr, corrector.get_logger(__name__, 40), 40
                )

    def test_km_scale_rewrite_is_dropped(self, tmp_path):
        out = self._corrections(
            tmp_path, CAMPAIGN_XYZ, (2627583.4397, -943252.7548, 5715821.3894)
        )
        assert "APPROX POSITION XYZ" not in out

    def test_other_corrections_survive_the_refusal(self, tmp_path):
        """Refusing the position must not discard the legitimate fixes."""
        out = self._corrections(
            tmp_path, CAMPAIGN_XYZ, (2627583.4397, -943252.7548, 5715821.3894)
        )
        assert out["MARKER NAME"] == ["ISAK"]

    def test_metre_scale_rewrite_still_applies(self, tmp_path):
        out = self._corrections(
            tmp_path, ISAK_XYZ, (2627583.4397 + 20, -943252.7548, 5715821.3894)
        )
        assert "APPROX POSITION XYZ" in out

    def test_the_two_paths_share_one_bound(self, tmp_path):
        from tostools.rinex.corrector import MAX_POSITION_CORRECTION_M

        assert MAX_POSITION_CORRECTION_M == _MAX_POSITION_CORRECTION_M
