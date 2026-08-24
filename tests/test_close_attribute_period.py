"""Tests for ``TOSWriter.close_attribute_period``.

The primitive behind "a device came off the mark". Installation-scoped values
— antenna height above the monument, the eccentricities, azimuth — stop being
true when the device is removed, and nothing succeeds them: kit in a warehouse
has no height above anything. So the period is CLOSED, not transitioned.

``transition_attribute_value`` is the wrong tool here; it would open a fresh
period and demand a value nobody has.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tostools.api.tos_writer import TOSWriter


def _make_writer() -> TOSWriter:
    return TOSWriter(dry_run=True, username="testuser", password="testpass")


def _writer_with(periods):
    w = _make_writer()
    w.get_attribute_values = MagicMock(return_value=periods)
    w.patch_attribute_value = MagicMock(return_value={"ok": True})
    return w


class TestClosesTheOpenPeriod:
    def test_patches_date_to_on_the_open_period(self):
        """The live ISAK 4527 shape: open since 2002, removed 2026-07-30."""
        w = _writer_with(
            [
                {
                    "id_attribute_value": 113122,
                    "date_from": "2002-01-09T00:00:00",
                    "date_to": None,
                }
            ]
        )
        assert w.close_attribute_period(4527, "antenna_height", "2026-07-30")
        w.patch_attribute_value.assert_called_once_with(113122, date_to="2026-07-30")

    def test_falls_back_to_the_id_key(self):
        """TOS returns the row id as `id` on some endpoints, `id_attribute_value`
        on others."""
        w = _writer_with([{"id": 113122, "date_from": "2002-01-09", "date_to": None}])
        w.close_attribute_period(4527, "antenna_height", "2026-07-30")
        w.patch_attribute_value.assert_called_once_with(113122, date_to="2026-07-30")

    def test_picks_the_latest_open_period_when_several_exist(self):
        """The invariant is one open period per code, but a corrupt entity must
        not make the close pick arbitrarily."""
        w = _writer_with(
            [
                {"id": 1, "date_from": "2002-01-09", "date_to": None},
                {"id": 2, "date_from": "2010-05-05", "date_to": None},
            ]
        )
        w.close_attribute_period(4527, "antenna_height", "2026-07-30")
        w.patch_attribute_value.assert_called_once_with(2, date_to="2026-07-30")

    def test_ignores_already_closed_periods(self):
        w = _writer_with(
            [
                {"id": 1, "date_from": "2002-01-09", "date_to": "2010-01-01"},
                {"id": 2, "date_from": "2010-01-01", "date_to": None},
            ]
        )
        w.close_attribute_period(4527, "antenna_height", "2026-07-30")
        w.patch_attribute_value.assert_called_once_with(2, date_to="2026-07-30")


class TestRefusesToCreateAnInvalidPeriod:
    def test_no_open_period_is_a_no_op(self):
        w = _writer_with(
            [{"id": 1, "date_from": "2002-01-09", "date_to": "2010-01-01"}]
        )
        assert w.close_attribute_period(4527, "antenna_height", "2026-07-30") is None
        w.patch_attribute_value.assert_not_called()

    def test_no_periods_at_all_is_a_no_op(self):
        w = _writer_with([])
        assert w.close_attribute_period(4527, "antenna_height", "2026-07-30") is None
        w.patch_attribute_value.assert_not_called()

    def test_period_starting_after_the_close_date_is_left_alone(self):
        """It belongs to a LATER installation — closing it here would both
        invert date_to <= date_from and corrupt the next site's record."""
        w = _writer_with(
            [{"id": 9, "date_from": "2026-09-01T00:00:00", "date_to": None}]
        )
        assert w.close_attribute_period(4527, "antenna_height", "2026-07-30") is None
        w.patch_attribute_value.assert_not_called()

    def test_period_starting_on_the_close_date_is_left_alone(self):
        """A zero-length period is not a record of anything."""
        w = _writer_with(
            [{"id": 9, "date_from": "2026-07-30T12:00:00", "date_to": None}]
        )
        assert w.close_attribute_period(4527, "antenna_height", "2026-07-30") is None
        w.patch_attribute_value.assert_not_called()

    def test_missing_row_id_is_a_no_op(self):
        w = _writer_with([{"date_from": "2002-01-09", "date_to": None}])
        assert w.close_attribute_period(4527, "antenna_height", "2026-07-30") is None
        w.patch_attribute_value.assert_not_called()


class TestComparisonIsDateOnly:
    def test_timestamps_compare_on_the_date_part(self):
        """TOS mixes '2002-01-09' and '2002-01-09 00:00:00' in one payload, so
        a raw string compare would misorder them."""
        w = _writer_with(
            [{"id": 3, "date_from": "2002-01-09T00:00:00", "date_to": None}]
        )
        assert w.close_attribute_period(4527, "antenna_height", "2026-07-30T12:00:00")
        w.patch_attribute_value.assert_called_once_with(
            3, date_to="2026-07-30T12:00:00"
        )
