"""Raw SBF is a named authority, not a hidden tier.

`tos audit constellations` reads the archived RINEX header when that is R3, and
decodes the day's raw SBF when it is R2 or unparseable — the only thing that can
answer the 2017-2025 span, since R2 under-reports constellations.

The decode produces an R3 reading, so `version` and `reliable` are
indistinguishable from a genuine R3 header. Without an explicit origin the
report would claim "archive RINEX 3.04" for a set the archived header never
contained.
"""

from tostools.constellation import ConstellationReading


class TestOriginField:
    def test_defaults_to_the_header(self):
        # Every existing construction site reads a RINEX header, so the default
        # must be that — adding the field cannot relabel existing readings.
        r = ConstellationReading(
            version=3.04, systems=frozenset({"GPS"}), reliable=True
        )
        assert r.origin == "rinex_header"

    def test_decode_labels_itself(self):
        r = ConstellationReading(
            version=3.04,
            systems=frozenset({"GPS", "GAL"}),
            reliable=True,
            source_path="/x/VMEY2026...sbf.gz",
            origin="sbf_decode",
        )
        assert r.origin == "sbf_decode"

    def test_a_decode_is_otherwise_indistinguishable(self):
        # This is WHY the field is needed: version and reliable match a genuine
        # R3 header exactly, so nothing else in the reading gives it away.
        header = ConstellationReading(3.04, frozenset({"GPS"}), True)
        decode = ConstellationReading(
            3.04, frozenset({"GPS"}), True, origin="sbf_decode"
        )
        assert (header.version, header.reliable) == (decode.version, decode.reliable)
        assert header.origin != decode.origin


class TestReportLabel:
    """The report must name which authority replied."""

    @staticmethod
    def _label(reading):
        # Mirrors the expression in tos.py's constellation report.
        return (
            "raw SBF decode"
            if getattr(reading, "origin", "") == "sbf_decode"
            else "archive RINEX"
        )

    def test_header_reads_as_archive(self):
        assert (
            self._label(ConstellationReading(3.04, frozenset(), True))
            == "archive RINEX"
        )

    def test_decode_reads_as_raw(self):
        r = ConstellationReading(3.04, frozenset(), True, origin="sbf_decode")
        assert self._label(r) == "raw SBF decode"

    def test_label_survives_a_reading_without_the_field(self):
        # getattr default: an old pickled/constructed reading must not crash the
        # report.
        class Legacy:
            version, reliable = 2.11, False

        assert self._label(Legacy()) == "archive RINEX"
