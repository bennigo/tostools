"""A single-file constellation reading must not silently date its periods.

The non-history verb reads the MOST RECENT daily RINEX. That establishes which
systems are on; it says nothing about when each started. But the ACTION lines it
emits run from the receiver's INSTALL date, which the reading cannot support.

Measured on VMEY 2026-08-18 — the single-file reading gave BDS+GAL+GLO+GPS and
proposed all four from 2017-07-11, while --history segmented the same archive as:

    GPS@2017-07-11  GLO@2017-07-11  GAL@2023-01-20  BDS@2024-02-16

so two systems would have been backdated by 5.5 and 6.5 years into TOS, and from
there into every regenerated RINEX header. GAL first appears nine days after the
2023-01-11 antenna/box replacement, so the archive and the visit log agree.
"""

import inspect

from tostools import tos as tos_mod


def _report_src() -> str:
    return inspect.getsource(tos_mod._audit_constellations_main)


class TestWarningPresence:
    def test_the_reading_is_called_single_file(self):
        assert "single-file reading" in _report_src()

    def test_it_separates_which_from_since_when(self):
        # The distinction IS the warning; losing it makes the line decorative.
        src = _report_src()
        assert "WHICH systems are on" in src
        assert "SINCE WHEN" in src

    def test_it_names_the_install_date_assumption(self):
        assert "install date by assumption" in _report_src()

    def test_it_points_at_the_history_verb(self):
        src = _report_src()
        assert "--history" in src
        assert "Confirm the start dates" in src


class TestSuggestedCommand:
    def test_it_echoes_the_typed_marker_not_the_station_name(self):
        # `tos audit constellations Vestmannaeyjar --history` is not what the
        # operator typed; the verb takes a marker. Echo args.name back.
        src = _report_src()
        assert "{args.name} --history" in src
        assert "report.station_name or '<STN>'} --history" not in src


class TestOriginLabelStillPresent:
    """The warning sits next to the authority label; neither should displace the other."""

    def test_both_survive(self):
        src = _report_src()
        assert "raw SBF decode" in src  # which authority answered
        assert "single-file reading" in src  # and how much of it was read
