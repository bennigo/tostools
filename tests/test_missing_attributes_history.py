"""Tests for auditing decommissioned devices (`missing-attributes --history`).

Retired devices were skipped entirely — "a removed device's missing attributes
aren't a current operational gap". True operationally, but their metadata is
still published: a retired antenna appears in IGS site-log section 4 and in the
header of every RINEX recorded while it was installed. ISAK has six previous
antennas whose gaps were invisible.

The sharp edge this also guards: a catalog `default_value` describing a device
IN SERVICE must not be proposed for one that is retired. `status` defaults to
"virkt" (active); applied in bulk from a triage file that would mark six
retired antennas as currently active.
"""

from __future__ import annotations

from tostools.audit_missing_attributes import (
    _CURRENT_STATE_CODES,
    StationMissingAttributesReport,
    _audit_entity,
)

# gps_relevance must be "yes" or _required_codes_in_scope filters the rule out.
RULES = {
    "status": {
        "gps_required_for": ["antenna"],
        "default_value": "virkt",
        "gps_relevance": "yes",
    },
    "azimuth": {
        "gps_required_for": ["antenna"],
        "default_value": "0.0",
        "gps_relevance": "yes",
    },
    "antenna_offset_north": {
        "gps_required_for": ["antenna"],
        "default_value": "0.0",
        "gps_relevance": "yes",
    },
}


def _run(*, decommissioned: bool):
    report = StationMissingAttributesReport(station_id=1, station_name="X")
    _audit_entity(
        report=report,
        scope_rules=RULES,
        history={"attributes": []},  # nothing recorded → everything missing
        entity_id=4520,
        entity_subtype="antenna",
        entity_label="190269",
        scope_name="devices",
        suggested_date_from="2001-05-30",
        decommissioned=decommissioned,
    )
    return {v.code: v.suggested_value for v in report.violations}


class TestDecommissionedDefaults:
    def test_status_default_is_suppressed_when_retired(self):
        """ "virkt" means active — proposing it for a retired device is false."""
        assert _run(decommissioned=True)["status"] is None

    def test_status_default_is_offered_when_in_service(self):
        assert _run(decommissioned=False)["status"] == "virkt"

    def test_historical_facts_keep_their_defaults(self):
        """Offsets and azimuth are facts about the install, not its state —
        suppressing them would force pointless hand-entry."""
        got = _run(decommissioned=True)
        assert got["azimuth"] == "0.0"
        assert got["antenna_offset_north"] == "0.0"

    def test_only_state_codes_are_suppressed(self):
        assert "status" in _CURRENT_STATE_CODES
        assert "azimuth" not in _CURRENT_STATE_CODES
        assert "antenna_offset_north" not in _CURRENT_STATE_CODES

    def test_every_required_code_is_still_reported(self):
        """Suppressing a suggestion must not drop the violation itself."""
        assert set(_run(decommissioned=True)) == set(RULES)


class TestCatalogStatusValue:
    def test_default_is_a_value_tos_actually_uses(self):
        """Regression: the catalog said "virk", missing the trailing t, so the
        audit proposed a value absent from TOS's own vocabulary."""
        import yaml

        from tostools.data_files import data_path

        cat = yaml.safe_load(open(data_path("attribute_codes.yaml")))
        entry = cat["devices"]["status"]
        assert entry["default_value"] == "virkt"
        assert entry["default_value"] in entry["sample_values"]
