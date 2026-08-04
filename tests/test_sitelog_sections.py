"""IGS site-log §3/§4 subsection numbering and session merging.

Two defects found on ISAK's generated log (2026-08-04), which had reached 3.17:

* ``f"3.{n}  "`` hard-codes two trailing spaces. Correct for 3.1–3.9, one column
  too wide from 3.10 on, so every field label after the tenth subsection sat out
  of line with the 5-space continuation rows beneath it.
* The device-history synthesis opens a window at every attribute-period
  boundary. A firmware change on 2026-08-01 plus a QZSS/SBAS closure on
  2026-08-02 produced a ONE-DAY subsection differing from its successor only in
  the satellite-system string.
"""

from __future__ import annotations

from tostools.gps_metadata_functions import _merge_equivalent_receiver_sessions


def _session(serial="3018434", fw="5.7.0", model="SEPT POLARX5", frm="", to=None):
    return {
        "device": {
            "code_entity_subtype": "gnss_receiver",
            "model": model,
            "serial_number": serial,
            "firmware_version": fw,
            "date_from": frm,
            "date_to": to,
        }
    }


class TestSubsectionAlignment:
    """The label field is a fixed 5 columns whatever the number's width."""

    def test_single_digit(self):
        assert f"{'3.1':<5}" == "3.1  "

    def test_double_digit_keeps_the_width(self):
        assert f"{'3.16':<5}" == "3.16 "
        assert len(f"{'3.16':<5}") == len(f"{'3.1':<5}") == 5

    def test_colon_column_matches_the_continuation_indent(self):
        """Continuation rows are 5 spaces + label; the header must match."""
        header = f"{'3.16':<5}Receiver Type            : X"
        cont = "     Satellite System         : Y"
        assert header.index(":") == cont.index(":")

    def test_regression_the_old_form_was_misaligned(self):
        old = "3.16  Receiver Type            : X"
        cont = "     Satellite System         : Y"
        assert old.index(":") != cont.index(":")


class TestMergeEquivalentSessions:
    def test_the_isak_case_collapses_to_one(self):
        """3.16 (one day) and 3.17 differ only in satellite system."""
        sessions = [
            _session(frm="2026-08-01", to="2026-08-02"),
            _session(frm="2026-08-02", to=None),
        ]
        merged = _merge_equivalent_receiver_sessions(sessions)
        assert len(merged) == 1

    def test_merged_row_keeps_the_earliest_start(self):
        sessions = [
            _session(frm="2026-08-01", to="2026-08-02"),
            _session(frm="2026-08-02", to=None),
        ]
        merged = _merge_equivalent_receiver_sessions(sessions)
        assert merged[0]["device"]["date_from"] == "2026-08-01"

    def test_merged_row_keeps_the_later_end(self):
        sessions = [
            _session(frm="2026-08-01", to="2026-08-02"),
            _session(frm="2026-08-02", to=None),
        ]
        merged = _merge_equivalent_receiver_sessions(sessions)
        assert merged[0]["device"]["date_to"] is None

    def test_firmware_change_is_never_merged(self):
        """The boundary a site log exists to record."""
        sessions = [
            _session(fw="5.6.0", frm="2026-02-16", to="2026-08-01"),
            _session(fw="5.7.0", frm="2026-08-01", to=None),
        ]
        assert len(_merge_equivalent_receiver_sessions(sessions)) == 2

    def test_receiver_swap_is_never_merged(self):
        sessions = [
            _session(serial="5207K82295", model="TRIMBLE NETR9", frm="2013-03-27"),
            _session(serial="3018434", frm="2017-07-03"),
        ]
        assert len(_merge_equivalent_receiver_sessions(sessions)) == 2

    def test_model_change_is_never_merged(self):
        sessions = [
            _session(model="SEPT POLARX5", frm="2017-07-03"),
            _session(model="SEPT MOSAIC-X5", frm="2024-01-01"),
        ]
        assert len(_merge_equivalent_receiver_sessions(sessions)) == 2

    def test_a_long_run_of_equivalents_collapses(self):
        sessions = [_session(frm=f"2026-08-{d:02d}") for d in range(1, 6)]
        merged = _merge_equivalent_receiver_sessions(sessions)
        assert len(merged) == 1
        assert merged[0]["device"]["date_from"] == "2026-08-01"

    def test_merge_then_real_change_then_merge(self):
        sessions = [
            _session(fw="5.6.0", frm="2026-01-01"),
            _session(fw="5.6.0", frm="2026-02-01"),
            _session(fw="5.7.0", frm="2026-08-01"),
            _session(fw="5.7.0", frm="2026-08-02"),
        ]
        merged = _merge_equivalent_receiver_sessions(sessions)
        assert len(merged) == 2
        assert merged[0]["device"]["date_from"] == "2026-01-01"
        assert merged[1]["device"]["date_from"] == "2026-08-01"

    def test_single_session_untouched(self):
        assert len(_merge_equivalent_receiver_sessions([_session()])) == 1

    def test_empty_input(self):
        assert _merge_equivalent_receiver_sessions([]) == []

    def test_input_is_not_mutated(self):
        """The caller's session dicts are shared with other §-builders."""
        sessions = [
            _session(frm="2026-08-01", to="2026-08-02"),
            _session(frm="2026-08-02", to=None),
        ]
        _merge_equivalent_receiver_sessions(sessions)
        assert sessions[1]["device"]["date_from"] == "2026-08-02"
