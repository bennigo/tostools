"""The dry-run preview must be the write, not a second opinion about it.

``receivers rinex --fix-headers`` previewed the value ``compare_rinex_to_tos``
proposed while the write used the value ``_get_corrections_from_tos`` built. For
a TOS placeholder antenna serial the two disagree — the preview said the serial
would be blank, the write put ``0000`` there (measured on 66 VMEY files,
2026-08-19). Nothing was harmed that time, but a dry-run exists precisely so an
archive rewrite can be reviewed before it happens, and a preview that does not
describe the action is worthless on the one run where it matters.

``resolve_corrections`` is now the single builder both paths call. These tests
pin that by writing a real file and asserting the bytes on disk are exactly what
``render_correction`` previewed.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from tostools.rinex.corrector import (
    STRIP_LINE,
    correct_rinex_from_tos,
    render_correction,
    resolve_corrections,
)

_HDR = (
    "     2.11           OBSERVATION DATA    M                   RINEX VERSION / TYPE\n"
    "VMEY                                                        MARKER NAME\n"
    "VMEY                                                        MARKER NUMBER\n"
    "BGO                 IMO                                     OBSERVER / AGENCY\n"
    "antenna-VMEY-2023011SEPCHOKE_B3E6   SPKE                    ANT # / TYPE\n"
    "        0.0000        0.0000        0.0000                  ANTENNA: DELTA H/E/N\n"
    "                                                            END OF HEADER\n"
)
_DATA = " 26  8  1  0  0  0.0000000  0  1G01\n  25213991.484 6\n"

#: What TOS yields for VMEY — placeholder antenna serial and a real DOMES.
_TOS = {
    "ANT # / TYPE": ["0000", "SEPCHOKE_B3E6   SPKE"],
    "MARKER NUMBER": ["10217M001"],
    "ANTENNA: DELTA H/E/N": [0.999, 0.0, 0.0],
}


@pytest.fixture
def rinex(tmp_path):
    p = tmp_path / "VMEY2130.26o"
    p.write_bytes((_HDR + _DATA).encode())
    return p


def _field(path, label):
    """The 60-char data portion of ``label``'s header line, or None if absent."""
    for line in path.read_text().splitlines():
        if line[60:].strip() == label:
            return line[:60]
    return None


def _patched(corrections):
    return patch(
        "tostools.rinex.corrector._get_corrections_from_tos",
        return_value=dict(corrections),
    )


class TestPreviewEqualsWrite:
    @pytest.mark.parametrize("label", sorted(_TOS))
    def test_written_field_is_byte_identical_to_the_preview(self, rinex, label):
        with _patched(_TOS):
            resolved = resolve_corrections(rinex, "VMEY", only_fields={label})
            previewed = render_correction(label, resolved[label])
            correct_rinex_from_tos(rinex, "VMEY", only_fields={label})
        assert _field(rinex, label) == previewed

    def test_the_placeholder_serial_case_that_started_this(self, rinex):
        # The preview must say 0000 because that is what lands in the file — not
        # blank, which is what the validator would have proposed.
        with _patched(_TOS):
            resolved = resolve_corrections(rinex, "VMEY", only_fields={"ANT # / TYPE"})
            previewed = render_correction("ANT # / TYPE", resolved["ANT # / TYPE"])
        assert previewed.startswith("0000")
        assert "antenna-VMEY" not in previewed, "the 21-char serial must never be written"
        # A20,A20: the type starts at column 21 with a clean separation.
        assert previewed[20:40].rstrip() == "SEPCHOKE_B3E6   SPKE".rstrip()

    def test_all_fields_together_match_their_previews(self, rinex):
        labels = set(_TOS)
        with _patched(_TOS):
            resolved = resolve_corrections(rinex, "VMEY", only_fields=labels)
            previews = {lbl: render_correction(lbl, resolved[lbl]) for lbl in labels}
            correct_rinex_from_tos(rinex, "VMEY", only_fields=labels)
        for lbl, expected in previews.items():
            assert _field(rinex, lbl) == expected, f"{lbl} written != previewed"


class TestResolveIsTheGate:
    def test_only_fields_filters_the_resolved_set(self, rinex):
        with _patched(_TOS):
            out = resolve_corrections(rinex, "VMEY", only_fields={"MARKER NUMBER"})
        assert set(out) == {"MARKER NUMBER"}

    def test_extra_corrections_are_merged_before_the_filter(self, rinex):
        # OBSERVER / AGENCY is injected by receivers (agencies.yaml is out of the
        # corrector's reach); the preview must see it exactly as the write does.
        extra = {"OBSERVER / AGENCY": ["GNSSatIMO", "Icelandic Meteorological Office"]}
        with _patched(_TOS):
            out = resolve_corrections(
                rinex,
                "VMEY",
                only_fields={"OBSERVER / AGENCY"},
                extra_corrections=extra,
            )
            previewed = render_correction("OBSERVER / AGENCY", out["OBSERVER / AGENCY"])
            correct_rinex_from_tos(
                rinex,
                "VMEY",
                only_fields={"OBSERVER / AGENCY"},
                extra_corrections=extra,
            )
        assert _field(rinex, "OBSERVER / AGENCY") == previewed

    def test_a_label_tos_cannot_build_is_absent_from_the_resolved_set(self, rinex):
        # header_fix drops these instead of reporting a fix that never happens.
        with _patched(_TOS):
            out = resolve_corrections(rinex, "VMEY", only_fields={"REC # / TYPE / VERS"})
        assert out == {}

    def test_empty_tos_resolves_to_nothing(self, rinex):
        with _patched({}):
            assert resolve_corrections(rinex, "VMEY") == {}


class TestStripLineIsPreviewedAsRemoval:
    def test_strip_sentinel_renders_as_none_not_blank(self):
        # "removed" and "written as empty" are different edits; a preview that
        # showed a blank field for a stripped MARKER NUMBER would misdescribe it.
        assert render_correction("MARKER NUMBER", STRIP_LINE) is None

    def test_a_stripped_marker_number_leaves_no_line(self, rinex):
        with _patched({"MARKER NUMBER": STRIP_LINE}):
            resolved = resolve_corrections(rinex, "VMEY", only_fields={"MARKER NUMBER"})
            assert render_correction("MARKER NUMBER", resolved["MARKER NUMBER"]) is None
            correct_rinex_from_tos(rinex, "VMEY", only_fields={"MARKER NUMBER"})
        assert _field(rinex, "MARKER NUMBER") is None


class TestWriteStillWorks:
    def test_correct_rinex_from_tos_returns_the_file_when_nothing_to_do(self, rinex):
        # The refactor moved two early returns into resolve_corrections; the
        # caller must still hand back the untouched file rather than None.
        with _patched({}):
            assert correct_rinex_from_tos(rinex, "VMEY") == rinex

    def test_observations_are_untouched_by_a_header_rewrite(self, rinex):
        with _patched(_TOS):
            correct_rinex_from_tos(rinex, "VMEY", only_fields=set(_TOS))
        body = rinex.read_text().split("END OF HEADER\n", 1)[1]
        assert body == _DATA

    def test_logging_does_not_explode_on_a_resolve_with_no_logger_arg(self, rinex):
        # resolve_corrections builds its own logger; a bare call must not raise.
        with _patched(_TOS):
            resolve_corrections(rinex, "VMEY", loglevel=logging.DEBUG)
