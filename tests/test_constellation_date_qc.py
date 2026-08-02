"""Tests for the constellation date-disagreement check.

Gap this closes: the history audit proposed `add-attribute-period` for codes TOS
*omits*, but said nothing about a code TOS *has* with a wrong date. That is the
harder error — a plausible-looking hand-entered date is invisible, whereas an
absent one is obvious. Real case: ISAK's GAL was recorded 2026-08-01 while the
archive proves the receiver logged Galileo from 2022-11-09.

Direction matters and is asymmetric on purpose. `first_seen` is the first
ARCHIVED file recording the system, so the true switch-on is at or BEFORE it:

  * TOS later than the archive  → contradiction, no gap can explain it → flag
  * TOS earlier than the archive → consistent with an archive gap → stay silent
"""

from __future__ import annotations

from datetime import date

from tostools.audit_constellations import (
    ReceiverPeriodConstellations,
    StationConstellationHistoryReport,
    _contradicted_dates,
    _recorded_from_in_period,
    format_history_triage,
)


def _history(*attrs):
    """Device history with (code, value, date_from, date_to) attribute rows."""
    return {
        "attributes": [
            {"code": c, "value": v, "date_from": df, "date_to": dt}
            for c, v, df, dt in attrs
        ]
    }


class TestRecordedFrom:
    def test_returns_the_open_period_start(self):
        h = _history(("GAL", "true", "2026-08-01T00:00:00", None))
        assert _recorded_from_in_period(h, "GAL", date(2017, 7, 4), None) == date(
            2026, 8, 1
        )

    def test_ignores_a_false_value(self):
        h = _history(("GAL", "false", "2026-08-01T00:00:00", None))
        assert _recorded_from_in_period(h, "GAL", date(2017, 7, 4), None) is None

    def test_ignores_a_different_code(self):
        h = _history(("BDS", "true", "2026-08-01T00:00:00", None))
        assert _recorded_from_in_period(h, "GAL", date(2017, 7, 4), None) is None

    def test_earliest_wins_when_several_overlap(self):
        h = _history(
            ("GAL", "true", "2024-01-01T00:00:00", "2025-01-01T00:00:00"),
            ("GAL", "true", "2025-01-01T00:00:00", None),
        )
        assert _recorded_from_in_period(h, "GAL", date(2017, 7, 4), None) == date(
            2024, 1, 1
        )

    def test_period_outside_the_window_is_ignored(self):
        """A decommissioned receiver's toggles must not leak into another period."""
        h = _history(("GAL", "true", "2010-01-01T00:00:00", "2011-01-01T00:00:00"))
        assert _recorded_from_in_period(h, "GAL", date(2017, 7, 4), None) is None


class TestContradiction:
    def test_flags_tos_later_than_the_archive(self):
        """The ISAK case: TOS 2026-08-01, archive proves 2022-11-09."""
        h = _history(("GAL", "true", "2026-08-01T00:00:00", None))
        got = _contradicted_dates(h, {"GAL": date(2022, 11, 9)}, date(2017, 7, 4), None)
        assert got == [("GAL", date(2026, 8, 1), date(2022, 11, 9))]

    def test_silent_when_tos_is_earlier(self):
        """An archive gap explains this — flagging it would be noise."""
        h = _history(("GAL", "true", "2020-01-01T00:00:00", None))
        assert _contradicted_dates(h, {"GAL": date(2022, 11, 9)}, None, None) == []

    def test_silent_on_an_exact_match(self):
        h = _history(("GAL", "true", "2022-11-09T00:00:00", None))
        assert _contradicted_dates(h, {"GAL": date(2022, 11, 9)}, None, None) == []

    def test_silent_when_tos_has_no_record(self):
        """That is the `missing` path's job, not this one — no double-report."""
        assert (
            _contradicted_dates(_history(), {"GAL": date(2022, 11, 9)}, None, None)
            == []
        )

    def test_reports_every_contradicted_code(self):
        h = _history(
            ("GAL", "true", "2026-08-01T00:00:00", None),
            ("BDS", "true", "2026-08-01T00:00:00", None),
            ("GPS", "true", "2017-07-04T00:00:00", None),  # correct — not flagged
        )
        got = _contradicted_dates(
            h,
            {
                "GAL": date(2022, 11, 9),
                "BDS": date(2025, 1, 27),
                "GPS": date(2017, 7, 4),
            },
            date(2017, 7, 4),
            None,
        )
        assert [c for c, _, _ in got] == ["GAL", "BDS"]  # sorted by evidence date

    def test_one_day_later_still_counts(self):
        """No fuzz: data on day N disproves a claim of N+1."""
        h = _history(("GAL", "true", "2022-11-10T00:00:00", None))
        assert len(_contradicted_dates(h, {"GAL": date(2022, 11, 9)}, None, None)) == 1


class TestTriageOutput:
    def _report(self, **kw):
        period = ReceiverPeriodConstellations(
            device_id=4972,
            serial="3018434",
            model="SEPT POLARX5",
            date_from=date(2017, 7, 4),
            date_to=None,
            reliable=True,
            **kw,
        )
        return StationConstellationHistoryReport(
            station_id=4346, station_name="Ísakot", marker="ISAK", periods=[period]
        )

    def test_emits_a_patch_action(self):
        rep = self._report(contradicted=[("GAL", date(2026, 8, 1), date(2022, 11, 9))])
        out = "\n".join(format_history_triage(rep))
        assert "ACTION 4972 patch-attribute-date GAL 2026-08-01 2022-11-09" in out

    def test_explains_the_disagreement_in_a_comment(self):
        rep = self._report(contradicted=[("GAL", date(2026, 8, 1), date(2022, 11, 9))])
        out = "\n".join(format_history_triage(rep))
        assert (
            "TOS says 2026-08-01" in out and "archive records it from 2022-11-09" in out
        )

    def test_contradiction_alone_triggers_output(self):
        """Previously a period with nothing 'missing' was skipped entirely."""
        rep = self._report(contradicted=[("GAL", date(2026, 8, 1), date(2022, 11, 9))])
        assert rep.has_actions
        assert format_history_triage(rep), "no triage emitted for a date-only finding"

    def test_nothing_emitted_when_all_agree(self):
        assert format_history_triage(self._report()) == []

    def test_both_kinds_coexist(self):
        rep = self._report(
            missing=[("QZSS", date(2025, 1, 27))],
            contradicted=[("GAL", date(2026, 8, 1), date(2022, 11, 9))],
        )
        out = "\n".join(format_history_triage(rep))
        assert "add-attribute-period QZSS true 2025-01-27 open" in out
        assert "patch-attribute-date GAL 2026-08-01 2022-11-09" in out
