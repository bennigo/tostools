"""Tests for the three defects that made the ISAK 2026-08-03 triage unsafe.

All three were found by applying a generated triage to live TOS and having to
retract it the same session:

* **D1** the file proposed OPEN periods for campaign antennas that had long
  since moved to other marks, asserting ISAK's geometry as their forever-truth.
* **D2** it proposed GAMIT ``station.info`` values for ``antenna_height`` and
  the offsets. Those are the STATION COMPOSITE (monument + ARP); the antenna
  entity carries only the delta. Eight rows went in ~1 m wrong.
* **D3** nothing ever noticed that a removed device's install-scoped attributes
  were still open — ISAK antenna 4527 left on 2026-07-30 with its
  ``antenna_height`` open since 2002-01-09.
"""

from __future__ import annotations

from tostools.audit_missing_attributes import (
    _INSTALL_SCOPED_CODES,
    _MONUMENT_BASELINE_CODES,
    StationMissingAttributesReport,
    _audit_entity,
    _collect_stale_open,
    _format_decimal,
    _is_unrecorded_monument_height,
    format_triage_file,
)

GEOMETRY_RULES = {
    "antenna_height": {
        "gps_required_for": ["antenna"],
        "default_value": None,
        "gps_relevance": "yes",
    },
    "antenna_offset_north": {
        "gps_required_for": ["antenna"],
        "default_value": "0.0",
        "gps_relevance": "yes",
    },
}


class _Occupation:
    """Minimal stand-in for a parsed GAMIT station.info occupation."""

    def __init__(self, height, north="0.0002", east="0.0001", htcod="DHARP"):
        self.antenna_height = height
        self.antenna_north = north
        self.antenna_east = east
        self.htcod = htcod


def _run(*, occupation=None, monument_baseline=None, date_to=None, rules=None):
    report = StationMissingAttributesReport(station_id=1, station_name="Ísakot")
    _audit_entity(
        report=report,
        scope_rules=rules if rules is not None else GEOMETRY_RULES,
        history={"attributes": []},
        entity_id=4520,
        entity_subtype="antenna",
        entity_label="190269",
        scope_name="devices",
        suggested_date_from="2001-06-18",
        suggested_date_to=date_to,
        occupation=occupation,
        monument_baseline=monument_baseline,
    )
    return {v.code: v for v in report.violations}


class TestTenureBounding:
    """D1 — a finished occupation must produce a CLOSED period."""

    def test_date_to_is_carried_onto_the_violation(self):
        got = _run(date_to="2001-06-21")
        assert got["antenna_height"].suggested_date_to == "2001-06-21"

    def test_still_installed_leaves_date_to_unset(self):
        assert _run()["antenna_height"].suggested_date_to is None

    def test_triage_emits_a_closed_period_verb(self):
        report = StationMissingAttributesReport(station_id=1, station_name="Ísakot")
        _audit_entity(
            report=report,
            scope_rules=GEOMETRY_RULES,
            history={"attributes": []},
            entity_id=4520,
            entity_subtype="antenna",
            entity_label="190269",
            scope_name="devices",
            suggested_date_from="2001-06-18",
            suggested_date_to="2001-06-21",
            occupation=_Occupation("1.0358"),
            monument_baseline={"monument_height": "1.0047"},
        )
        text = format_triage_file(report, generated_at="2026-08-03T00:00:00+00:00")
        assert (
            "ACTION 4520 add-attribute-period antenna_height 0.0311 "
            "2001-06-18 2001-06-21" in text
        )
        # The open-period verb must NOT appear for a finished occupation —
        # that is precisely the line that had to be retracted.
        assert "add-attribute antenna_height" not in text

    def test_triage_emits_an_open_period_when_still_installed(self):
        report = StationMissingAttributesReport(station_id=1, station_name="Ísakot")
        _audit_entity(
            report=report,
            scope_rules=GEOMETRY_RULES,
            history={"attributes": []},
            entity_id=21715,
            entity_subtype="antenna",
            entity_label="2505010005",
            scope_name="devices",
            suggested_date_from="2026-07-30",
        )
        text = format_triage_file(report, generated_at="2026-08-03T00:00:00+00:00")
        assert "add-attribute antenna_height" in text
        assert "add-attribute-period antenna_height" not in text


class TestMonumentRelativeGeometry:
    """D2 — station.info is the composite; TOS wants the ARP delta."""

    def test_monument_height_is_subtracted(self):
        got = _run(
            occupation=_Occupation("1.0358"),
            monument_baseline={"monument_height": "1.0047"},
        )
        assert got["antenna_height"].suggested_value == "0.0311"

    def test_subtraction_is_exact_not_float(self):
        """1.0358 - 1.0047 in binary floats is 0.031099999999999906."""
        got = _run(
            occupation=_Occupation("1.0358"),
            monument_baseline={"monument_height": "1.0047"},
        )
        assert "9999" not in got["antenna_height"].suggested_value

    def test_antenna_flush_on_the_monument_reads_zero(self):
        """ISAK occupation 1: composite == monument height, so ARP is 0.0 —
        which is exactly what `cfg replace-antenna` writes."""
        got = _run(
            occupation=_Occupation("1.0047"),
            monument_baseline={"monument_height": "1.0047"},
        )
        assert got["antenna_height"].suggested_value == "0.0"

    def test_unrecorded_monument_height_is_not_subtracted(self):
        """ISAK's campaign-era monuments all read '0.000' — a placeholder, not
        a survey. Subtracting it would dress the composite up as a delta."""
        got = _run(
            occupation=_Occupation("0.9083"),
            monument_baseline={"monument_height": "0.000"},
        )
        assert got["antenna_height"].suggested_value == "0.9083"
        assert "unrecorded" in got["antenna_height"].value_basis

    def test_zero_offset_baseline_IS_subtracted(self):
        """The asymmetry: a zero monument OFFSET is a real measurement, unlike
        a zero monument height."""
        got = _run(
            occupation=_Occupation("1.0", north="0.0002"),
            monument_baseline={"antenna_offset_north": "0.0"},
        )
        assert got["antenna_offset_north"].suggested_value == "0.0002"
        assert "monument-relative" in got["antenna_offset_north"].value_basis

    def test_no_monument_at_all_keeps_the_composite(self):
        got = _run(occupation=_Occupation("0.9083"), monument_baseline=None)
        assert got["antenna_height"].suggested_value == "0.9083"
        assert "no monument covers" in got["antenna_height"].value_basis

    def test_monument_present_but_axis_unrecorded_says_so(self):
        """Distinct from 'no monument' — this gap is one somebody can fill."""
        got = _run(occupation=_Occupation("0.9083"), monument_baseline={})
        assert got["antenna_height"].suggested_value == "0.9083"
        assert "no open monument_height" in got["antenna_height"].value_basis

    def test_catalog_default_is_untouched_without_station_info(self):
        """No occupation → no composite → nothing to de-composite."""
        got = _run(monument_baseline={"antenna_offset_north": "0.0002"})
        assert got["antenna_offset_north"].suggested_value == "0.0"
        assert got["antenna_offset_north"].value_basis is None

    def test_reference_point_is_not_a_geometry_number(self):
        assert "antenna_reference_point" not in _MONUMENT_BASELINE_CODES


class TestUnrecordedMonumentHeight:
    def test_only_height_treats_zero_as_unrecorded(self):
        assert _is_unrecorded_monument_height("monument_height", "0.000")
        assert _is_unrecorded_monument_height("monument_height", "0")
        assert not _is_unrecorded_monument_height("antenna_offset_north", "0.0")

    def test_a_real_height_is_kept(self):
        assert not _is_unrecorded_monument_height("monument_height", "1.0047")

    def test_unparseable_is_not_treated_as_zero(self):
        assert not _is_unrecorded_monument_height("monument_height", "n/a")


class TestFormatDecimal:
    def test_keeps_one_decimal_on_a_zero(self):
        from decimal import Decimal

        assert _format_decimal(Decimal("0.0000")) == "0.0"

    def test_strips_trailing_zeros(self):
        from decimal import Decimal

        assert _format_decimal(Decimal("0.03110")) == "0.0311"

    def test_keeps_survey_precision(self):
        from decimal import Decimal

        assert _format_decimal(Decimal("1.0047")) == "1.0047"


class TestStaleOpenAttributes:
    """D3 — install-scoped values left open after the device was removed."""

    def _collect(self, attributes, removal="2026-07-30"):
        report = StationMissingAttributesReport(station_id=1, station_name="Ísakot")
        _collect_stale_open(
            report=report,
            history={"attributes": attributes},
            entity_id=4527,
            entity_subtype="antenna",
            entity_label="262509",
            removal_date=removal,
        )
        return {s.code: s for s in report.stale_open}

    def test_open_antenna_height_after_removal_is_flagged(self):
        """The live ISAK 4527 case: removed 2026-07-30, height open since 2002."""
        got = self._collect(
            [
                {
                    "code": "antenna_height",
                    "value": "0.000",
                    "date_from": "2002-01-09T00:00:00",
                    "date_to": None,
                }
            ]
        )
        assert got["antenna_height"].date_from == "2002-01-09"
        assert got["antenna_height"].removal_date == "2026-07-30"

    def test_already_closed_period_is_not_flagged(self):
        got = self._collect(
            [
                {
                    "code": "antenna_height",
                    "value": "0.000",
                    "date_from": "2002-01-09T00:00:00",
                    "date_to": "2026-07-30T00:00:00",
                }
            ]
        )
        assert got == {}

    def test_device_state_codes_stay_open(self):
        """status/comment/owner describe the device wherever it now is."""
        got = self._collect(
            [
                {
                    "code": code,
                    "value": "x",
                    "date_from": "2026-07-30T12:00:00",
                    "date_to": None,
                }
                for code in ("status", "comment", "owner")
            ]
        )
        assert got == {}

    def test_period_opened_after_removal_belongs_elsewhere(self):
        """A value opened after it left here describes its NEXT installation."""
        got = self._collect(
            [
                {
                    "code": "antenna_height",
                    "value": "1.2",
                    "date_from": "2026-09-01T00:00:00",
                    "date_to": None,
                }
            ]
        )
        assert got == {}

    def test_install_scoped_set_is_the_geometry_group(self):
        assert _INSTALL_SCOPED_CODES == {
            "antenna_height",
            "antenna_offset_north",
            "antenna_offset_east",
            "azimuth",
        }
        # Classified `inherent` in the catalog — the DHARP convention travels
        # with the antenna model, so it is not installation-scoped.
        assert "antenna_reference_point" not in _INSTALL_SCOPED_CODES

    def test_triage_renders_the_close_action(self):
        report = StationMissingAttributesReport(station_id=1, station_name="Ísakot")
        _collect_stale_open(
            report=report,
            history={
                "attributes": [
                    {
                        "code": "antenna_height",
                        "value": "0.000",
                        "date_from": "2002-01-09T00:00:00",
                        "date_to": None,
                    }
                ]
            },
            entity_id=4527,
            entity_subtype="antenna",
            entity_label="262509",
            removal_date="2026-07-30",
        )
        text = format_triage_file(report, generated_at="2026-08-03T00:00:00+00:00")
        assert (
            "ACTION 4527 patch-attribute-date-to antenna_height "
            "2002-01-09 2026-07-30" in text
        )
        assert "STILL OPEN AFTER REMOVAL" in text

    def test_no_section_when_nothing_is_stale(self):
        report = StationMissingAttributesReport(station_id=1, station_name="Ísakot")
        text = format_triage_file(report, generated_at="2026-08-03T00:00:00+00:00")
        assert "STILL OPEN AFTER REMOVAL" not in text
