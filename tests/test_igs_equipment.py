"""Regression tests for IGS equipment-name lookups (igs_equipment)."""

from tostools.standards.igs_equipment import to_igs_antenna, to_igs_receiver


class TestMosaicX5:
    def test_mosaic_x5_uses_hyphenated_rcvr_ant_tab_name(self):
        # rcvr_ant.tab spells it "SEPT MOSAIC-X5" (hyphen), not "SEPT MOSAICX5".
        assert to_igs_receiver("mosaic-X5") == "SEPT MOSAIC-X5"

    def test_mosaic_x5_aliases(self):
        for alias in ("mosaicX5", "MOSAIC-X5", "MOSAICX5"):
            assert to_igs_receiver(alias) == "SEPT MOSAIC-X5"

    def test_canonical_mosaic_passthrough(self):
        assert to_igs_receiver("SEPT MOSAIC-X5") == "SEPT MOSAIC-X5"


class TestAntennaPassthrough:
    def test_listed_antenna(self):
        assert to_igs_antenna("TRM115000.10") == "TRM115000.10"

    def test_canonical_identity_passthrough(self):
        # A name already in the table as a value resolves to itself even when not
        # an explicit key (mirrors to_igs_receiver's identity step).
        assert to_igs_antenna("TRM57971.00") == "TRM57971.00"

    def test_unknown_antenna_still_none(self):
        assert to_igs_antenna("DEFINITELY_NOT_AN_ANTENNA") is None


class TestVeraChoke:
    """SEPVC6150L — Septentrio VeraChoke, deployed at HOLV (Hólmavík).

    Missing from ANTENNA_IGS until 2026-07, which made every `cfg` verb that
    validates a model unusable for that station. IGS rcvr_ant.tab canonical
    spelling, added there 20 Apr 2020.
    """

    def test_verachoke_is_igs_valid(self):
        assert to_igs_antenna("SEPVC6150L") == "SEPVC6150L"

    def test_verachoke_case_insensitive(self):
        assert to_igs_antenna("sepvc6150l") == "SEPVC6150L"

    def test_not_confused_with_the_veraphase_cone(self):
        # SEPVP6050_CONE landed in rcvr_ant.tab the same day; the fleet doesn't
        # run it, so it must NOT silently resolve.
        assert to_igs_antenna("SEPVP6050_CONE") is None


class TestNgsOnlyAntennas:
    """Antennas the fleet runs that are NGS-calibrated but not IGS-registered.

    ``ANTENNA_IGS`` gates every `receivers cfg` verb that writes a model, so an
    antenna missing here makes those verbs unusable for its stations. The fleet
    runs several that appear in NGS ``ngs20.atx`` but not IGS ``rcvr_ant.tab``;
    both files were grepped directly (not via a search summariser) when these
    were added.
    """

    def test_aerat2775_42_is_accepted(self):
        # ICEB, ICEC, KVIS, SAVI. NGS FIELD/NGS 26-JUL-01.
        assert to_igs_antenna("AERAT2775_42") == "AERAT2775_42"

    def test_aerat2775_42_and_43_are_distinct_calibrations(self):
        """The one-digit difference is two different antennas, not a typo.

        IGS carries only _43; NGS carries both, with different calibration
        methods and epochs (FIELD/NGS 2001 vs ROBOT/Geo++ 2017). Collapsing one
        into the other would swap in the wrong phase-centre model — a silent
        position bias, which is exactly what this table exists to prevent.
        """
        assert to_igs_antenna("AERAT2775_42") == "AERAT2775_42"
        assert to_igs_antenna("AERAT2775_42") != to_igs_antenna("AERAT2775_43")

    def test_as_ant3bcal01_is_its_own_antenna(self):
        # BLAL. NGS FIELD/NGS 16-NOV-20 — distinct from AS-ANT3BCAL (27-OCT-20).
        assert to_igs_antenna("AS-ANT3BCAL01") == "AS-ANT3BCAL01"
        assert to_igs_antenna("AS-ANT3BCAL01") != to_igs_antenna("AS-ANT3BCAL")

    def test_navxperience_3g_plus_c_is_accepted(self):
        # The fleet's largest single antenna population (10 stations).
        # In BOTH igs20.atx and rcvr_ant.tab.
        assert to_igs_antenna("NAX3G+C") == "NAX3G+C"

    def test_plus_sign_in_name_survives_lookup(self):
        assert to_igs_antenna("nax3g+c") == "NAX3G+C"
