"""`tos audit attribute-catalog` — catalog vs the TOS attribute-type table.

No network: the schema dict is the unit under test's input, and the
catalog is written to a tmp file. The live shape is pinned by
`test_fetch_schema_codes_collapses_entity_type_rows`, which feeds the
aggregator the exact row shape `/admin_attribute_rows` returns.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tostools.audit_attribute_catalog import (
    WRITE_REACHING_FIELDS,
    CatalogAuditReport,
    audit_attribute_catalog,
)


def _catalog(tmp_path: Path, stations=None, devices=None, locations=None) -> Path:
    path = tmp_path / "attribute_codes.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "stations": stations or {},
                "devices": devices or {},
                "locations": locations or {},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


def _schema(**codes):
    """`{code: {"label": ..., "entity_types": [...]}}` as the fetcher returns.

    Defaults to a code defined for every scope, so a test that does not care
    about scope is not accidentally testing it.
    """
    return {
        code: {
            "label": label,
            "entity_types": ["station", "device", "infrastructure", "location"],
        }
        for code, label in codes.items()
    }


def _scoped_schema(code, label, entity_types):
    return {code: {"label": label, "entity_types": list(entity_types)}}


class TestPhantomDetection:
    def test_a_code_tos_does_not_define_is_phantom(self, tmp_path):
        cat = _catalog(tmp_path, stations={"close_date": {"icelandic_label": "X"}})
        report = audit_attribute_catalog(_schema(marker="Auðkenni"), catalog_path=cat)
        assert [p.code for p in report.phantom] == ["close_date"]

    def test_a_defined_code_is_not_phantom(self, tmp_path):
        cat = _catalog(tmp_path, stations={"marker": {"icelandic_label": "Auðkenni"}})
        report = audit_attribute_catalog(_schema(marker="Auðkenni"), catalog_path=cat)
        assert report.phantom == []

    def test_observation_is_NOT_the_test(self, tmp_path):
        """A code no entity carries is still valid if TOS defines it.

        This is the distinction the verb exists to make: `--attribute-list`
        aggregates over carried values and cannot tell 'undefined' from
        'defined but unpopulated'.
        """
        cat = _catalog(tmp_path, stations={"close_date": {"icelandic_label": "X"}})
        report = audit_attribute_catalog(
            _schema(close_date="X"), catalog_path=cat, observed_codes=set()
        )
        assert report.phantom == []

    def test_same_label_surfaces_the_rename_candidate(self, tmp_path):
        cat = _catalog(
            tmp_path, stations={"close_date": {"icelandic_label": "Lokadagsetning"}}
        )
        report = audit_attribute_catalog(
            _schema(date_end="Lokadagsetning"), catalog_path=cat
        )
        assert report.phantom[0].same_label_as == ["date_end"]

    def test_no_label_match_means_no_rename_candidate(self, tmp_path):
        cat = _catalog(tmp_path, stations={"station_ip": {"icelandic_label": "Nope"}})
        report = audit_attribute_catalog(_schema(marker="Auðkenni"), catalog_path=cat)
        assert report.phantom[0].same_label_as == []

    def test_every_scope_is_walked(self, tmp_path):
        cat = _catalog(
            tmp_path,
            stations={"a": {}},
            devices={"b": {}},
            locations={"c": {}},
        )
        report = audit_attribute_catalog(_schema(marker="M"), catalog_path=cat)
        assert {p.scope for p in report.phantom} == {
            "stations",
            "devices",
            "locations",
        }


class TestSeverity:
    """Severity follows blast radius — a write-reaching phantom is an error."""

    @pytest.mark.parametrize("field", WRITE_REACHING_FIELDS)
    def test_write_reaching_phantom_is_an_error(self, tmp_path, field):
        cat = _catalog(
            tmp_path,
            stations={"ghost": {"gps_relevance": "yes", field: ["geophysical"]}},
        )
        report = audit_attribute_catalog(_schema(marker="M"), catalog_path=cat)
        assert report.phantom[0].severity == "error"
        assert report.phantom[0].write_reaching == [field]
        assert len(report.errors) == 1

    def test_gps_relevant_phantom_is_a_warning(self, tmp_path):
        cat = _catalog(tmp_path, stations={"ghost": {"gps_relevance": "yes"}})
        report = audit_attribute_catalog(_schema(marker="M"), catalog_path=cat)
        assert report.phantom[0].severity == "warning"
        assert report.errors == []

    def test_unclassified_phantom_is_info(self, tmp_path):
        cat = _catalog(tmp_path, stations={"ghost": {"gps_relevance": "no"}})
        report = audit_attribute_catalog(_schema(marker="M"), catalog_path=cat)
        assert report.phantom[0].severity == "info"

    def test_an_empty_required_list_does_not_reach_a_write(self, tmp_path):
        """`gps_required_for: []` is the catalog's 'unclassified', not a rule."""
        cat = _catalog(
            tmp_path,
            stations={"ghost": {"gps_relevance": "yes", "gps_required_for": []}},
        )
        report = audit_attribute_catalog(_schema(marker="M"), catalog_path=cat)
        assert report.phantom[0].severity == "warning"


class TestUnlisted:
    def test_observed_code_absent_from_catalog_is_reported(self, tmp_path):
        cat = _catalog(tmp_path, stations={"marker": {}})
        report = audit_attribute_catalog(
            _schema(marker="M", date_end="Lokadagsetning"),
            catalog_path=cat,
            observed_codes={"date_end"},
        )
        assert [u.code for u in report.unlisted] == ["date_end"]

    def test_unobserved_schema_code_is_not_reported_by_default(self, tmp_path):
        """Other disciplines' vocabulary is not this catalog's business."""
        cat = _catalog(tmp_path, stations={"marker": {}})
        report = audit_attribute_catalog(
            _schema(marker="M", wmo="WMO"),
            catalog_path=cat,
            observed_codes=set(),
        )
        assert report.unlisted == []

    def test_all_unlisted_reports_it(self, tmp_path):
        cat = _catalog(tmp_path, stations={"marker": {}})
        report = audit_attribute_catalog(
            _schema(marker="M", wmo="WMO"), catalog_path=cat, observed_codes=None
        )
        assert [u.code for u in report.unlisted] == ["wmo"]

    def test_a_code_listed_in_any_scope_is_not_unlisted(self, tmp_path):
        """Scopes share one namespace against the schema."""
        cat = _catalog(tmp_path, devices={"note": {}})
        report = audit_attribute_catalog(
            _schema(note="Glósur"), catalog_path=cat, observed_codes={"note"}
        )
        assert report.unlisted == []


class TestExitSemantics:
    def test_clean_catalog_has_no_findings(self, tmp_path):
        cat = _catalog(tmp_path, stations={"marker": {}})
        report = audit_attribute_catalog(
            _schema(marker="M"), catalog_path=cat, observed_codes={"marker"}
        )
        assert not report.has_findings

    def test_phantom_alone_is_a_finding(self, tmp_path):
        cat = _catalog(tmp_path, stations={"ghost": {}})
        report = audit_attribute_catalog(_schema(marker="M"), catalog_path=cat)
        assert report.has_findings

    def test_missing_catalog_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            audit_attribute_catalog(
                _schema(marker="M"), catalog_path=tmp_path / "nope.yaml"
            )


class TestSchemaFetch:
    def test_fetch_schema_codes_collapses_entity_type_rows(self, monkeypatch):
        """One row per (code, entity_type) — a code spanning scopes is ONE entry.

        Pinned against the real payload shape: `model` is id 27 for devices
        and 59 for monuments, so a naive dict build would drop one.
        """
        from tostools import audit_attribute_catalog as mod

        rows = [
            {"code": "model", "name_is": "Tegund", "id_entity_type": 4},
            {"code": "model", "name_is": "Tegund", "id_entity_type": 9},
            {"code": "marker", "name_is": "Auðkenni", "id_entity_type": 1},
            {"code": None, "name_is": "junk"},
        ]

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return rows

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        schema = mod.fetch_schema_codes()
        assert set(schema) == {"model", "marker"}
        assert sorted(schema["model"]["entity_types"]) == [4, 9]
        assert schema["marker"]["label"] == "Auðkenni"


class TestReportShape:
    def test_counts_distinct_codes_not_scope_rows(self, tmp_path):
        """`note` in two scopes is one code, counted once."""
        cat = _catalog(tmp_path, stations={"note": {}}, devices={"note": {}})
        report = audit_attribute_catalog(_schema(marker="M"), catalog_path=cat)
        assert report.catalog_codes == 1
        assert len(report.phantom) == 2  # but reported per scope, since each is an edit

    def test_empty_report_is_clean(self):
        assert not CatalogAuditReport().has_findings


class TestScopeAwareness:
    """TOS keys attributes by (code, entity_type) — bare membership is unsound.

    A catalog entry naming a code TOS defines only for some OTHER entity type
    is still wrong, and the bare-membership version of this verb called it
    clean. That is the same class of miss the verb exists to catch, so it is
    checked rather than assumed.
    """

    def test_code_defined_for_another_entity_type_is_still_phantom(self, tmp_path):
        cat = _catalog(tmp_path, devices={"marker": {"icelandic_label": "Auðkenni"}})
        report = audit_attribute_catalog(
            _scoped_schema("marker", "Auðkenni", ["station"]), catalog_path=cat
        )
        assert [p.code for p in report.phantom] == ["marker"]
        assert report.phantom[0].wrong_scope is True
        assert report.phantom[0].defined_for == ["station"]

    def test_code_defined_for_this_scope_is_clean(self, tmp_path):
        cat = _catalog(tmp_path, stations={"marker": {}})
        report = audit_attribute_catalog(
            _scoped_schema("marker", "Auðkenni", ["station"]),
            catalog_path=cat,
            observed_codes={"marker"},
        )
        assert report.phantom == []

    def test_devices_scope_spans_infrastructure(self, tmp_path):
        """A monument is Innviði — entity type `infrastructure`, not `device`."""
        cat = _catalog(tmp_path, devices={"subtype": {}})
        report = audit_attribute_catalog(
            _scoped_schema("subtype", "Undirtegund", ["infrastructure"]),
            catalog_path=cat,
            observed_codes={"subtype"},
        )
        assert report.phantom == []

    def test_a_null_entity_type_satisfies_every_scope(self, tmp_path):
        """`_resolve_id_attribute` rule 2 — a cross-scope catalog entry."""
        cat = _catalog(tmp_path, locations={"anything": {}})
        report = audit_attribute_catalog(
            _scoped_schema("anything", "X", [None]),
            catalog_path=cat,
            observed_codes={"anything"},
        )
        assert report.phantom == []

    def test_an_invented_name_is_phantom_but_not_wrong_scope(self, tmp_path):
        """The two failures are distinct and get different remedies."""
        cat = _catalog(tmp_path, stations={"ghost": {}})
        report = audit_attribute_catalog(
            _scoped_schema("marker", "Auðkenni", ["station"]), catalog_path=cat
        )
        assert report.phantom[0].wrong_scope is False
        assert report.phantom[0].defined_for == []

    def test_unknown_scope_is_not_flagged(self, tmp_path):
        """An unmapped catalog key would otherwise report every code it holds."""
        from tostools.audit_attribute_catalog import _defined_for_scope

        assert _defined_for_scope({"entity_types": ["station"]}, "nonesuch") is True


class TestFormLabelOnlyEntries:
    """A `form_label_only` entry documents a TOS WEB-FORM label that has no
    /admin_attribute_rows code behind it — the monument aliases, where the
    form's "Undirtegund"/"Tegund innviða" are the API's `subtype`/`model`.

    Having no schema code is the POINT of such an entry, so reporting it as a
    phantom every run is permanent known noise that a real typo then has to be
    spotted against. The mapping it claims is checked instead.
    """

    def test_form_label_entry_is_not_a_phantom(self, tmp_path):
        cat = _catalog(
            tmp_path,
            devices={
                "infrastructure_subtype": {
                    "icelandic_label": "Undirtegund",
                    "form_label_only": True,
                    "api_code": "subtype",
                }
            },
        )
        report = audit_attribute_catalog(
            _schema(subtype="Undirtegund"), catalog_path=cat
        )
        assert report.phantom == []
        assert report.broken_alias == []

    def test_a_mapping_to_an_undefined_code_is_reported(self, tmp_path):
        """The exemption buys an obligation: say where it maps, correctly."""
        cat = _catalog(
            tmp_path,
            devices={
                "infrastructure_type": {
                    "icelandic_label": "Tegund innviða",
                    "form_label_only": True,
                    "api_code": "no_such_code",
                }
            },
        )
        report = audit_attribute_catalog(_schema(model="Tegund"), catalog_path=cat)
        assert report.phantom == []
        assert len(report.broken_alias) == 1
        alias = report.broken_alias[0]
        assert (alias.scope, alias.code, alias.api_code) == (
            "devices",
            "infrastructure_type",
            "no_such_code",
        )
        assert report.has_findings, "a broken alias must not exit clean"

    def test_form_label_entry_without_api_code_is_still_exempt(self, tmp_path):
        """Nothing to verify — but it must not resurface as a phantom."""
        cat = _catalog(
            tmp_path,
            devices={
                "legacy_form_field": {"icelandic_label": "X", "form_label_only": True}
            },
        )
        report = audit_attribute_catalog(_schema(marker="M"), catalog_path=cat)
        assert report.phantom == []
        assert report.broken_alias == []

    def test_an_ordinary_entry_is_unaffected(self, tmp_path):
        """The exemption must key on the flag, not leak to every entry."""
        cat = _catalog(
            tmp_path, devices={"invented_code": {"icelandic_label": "Undirtegund"}}
        )
        report = audit_attribute_catalog(
            _schema(subtype="Undirtegund"), catalog_path=cat
        )
        assert [p.code for p in report.phantom] == ["invented_code"]
