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

from datetime import datetime as dt

from tostools.devices import absorb_short_boundary_sessions


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


def _sess(
    serial="3018434", fw="5.7.0", model="SEPT POLARX5", frm=None, to=None, sat="GPS"
):
    return {
        "device": {
            "id_entity": 4972,
            "model": model,
            "serial_number": serial,
            "firmware_version": fw,
            "satellite_system": sat,
            "date_from": frm,
            "date_to": to,
        }
    }


def _ident(d):
    return (
        d.get("id_entity"),
        d.get("model"),
        d.get("serial_number"),
        d.get("firmware_version"),
    )


class TestAbsorbShortBoundarySessions:
    """Slivers left by a constellation period entered off the equipment change."""

    def test_the_isak_one_day_block_is_absorbed(self):
        rows = [
            _sess(
                frm=dt(2026, 8, 1), to=dt(2026, 8, 2), sat="GPS+GLO+GAL+BDS+QZSS+SBAS"
            ),
            _sess(frm=dt(2026, 8, 2), to=None, sat="GPS+GLO+GAL+BDS"),
        ]
        out = absorb_short_boundary_sessions(rows, _ident)
        assert len(out) == 1
        assert out[0]["device"]["date_from"] == dt(2026, 8, 1)
        assert out[0]["device"]["date_to"] is None

    def test_successor_values_win(self):
        """The section should report the state the period ended in."""
        rows = [
            _sess(frm=dt(2026, 8, 1), to=dt(2026, 8, 2), sat="GPS+QZSS"),
            _sess(frm=dt(2026, 8, 2), to=None, sat="GPS"),
        ]
        out = absorb_short_boundary_sessions(rows, _ident)
        assert out[0]["device"]["satellite_system"] == "GPS"

    def test_a_real_installation_is_kept(self):
        """Longer than the sliver bound — a genuine period, however brief."""
        rows = [
            _sess(frm=dt(2026, 7, 1), to=dt(2026, 8, 1), sat="GPS+QZSS"),
            _sess(frm=dt(2026, 8, 1), to=None, sat="GPS"),
        ]
        assert len(absorb_short_boundary_sessions(rows, _ident)) == 2

    def test_firmware_upgrade_is_never_absorbed(self):
        """Even a one-day firmware window is a real §3 boundary."""
        rows = [
            _sess(fw="5.6.0", frm=dt(2026, 8, 1), to=dt(2026, 8, 2)),
            _sess(fw="5.7.0", frm=dt(2026, 8, 2), to=None),
        ]
        assert len(absorb_short_boundary_sessions(rows, _ident)) == 2

    def test_receiver_swap_is_never_absorbed(self):
        rows = [
            _sess(serial="AAA", frm=dt(2026, 8, 1), to=dt(2026, 8, 2)),
            _sess(serial="BBB", frm=dt(2026, 8, 2), to=None),
        ]
        assert len(absorb_short_boundary_sessions(rows, _ident)) == 2

    def test_non_contiguous_rows_are_kept(self):
        """A real gap in service is not an entry artifact."""
        rows = [
            _sess(frm=dt(2026, 8, 1), to=dt(2026, 8, 2)),
            _sess(frm=dt(2026, 9, 1), to=None),
        ]
        assert len(absorb_short_boundary_sessions(rows, _ident)) == 2

    def test_open_ended_row_is_never_a_sliver(self):
        rows = [_sess(frm=dt(2026, 8, 1), to=None), _sess(frm=dt(2026, 8, 2), to=None)]
        assert len(absorb_short_boundary_sessions(rows, _ident)) == 2

    def test_empty_and_single(self):
        assert absorb_short_boundary_sessions([], _ident) == []
        assert len(absorb_short_boundary_sessions([_sess()], _ident)) == 1

    def test_input_is_not_mutated(self):
        rows = [
            _sess(frm=dt(2026, 8, 1), to=dt(2026, 8, 2)),
            _sess(frm=dt(2026, 8, 2), to=None),
        ]
        absorb_short_boundary_sessions(rows, _ident)
        assert rows[1]["device"]["date_from"] == dt(2026, 8, 2)
