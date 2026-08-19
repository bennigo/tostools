"""Unit tests for :mod:`tostools.search` and the ``tos search`` CLI.

All TOS interaction is mocked — no network. The fake client mirrors the
two response shapes the search engine consumes:

- ``list_stations()`` → bulk ``/entity/search/station/geophysical/``
  objects (``attributes`` with ``code`` / ``value`` / ``date_from`` /
  ``date_to``);
- ``get_entity_history()`` → ``/history/entity/<id>/`` payloads
  (``children_connections`` for stations, open attributes for devices).
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional
from unittest.mock import patch

import pytest

from tostools.search import (
    DeviceSpec,
    Predicate,
    attribute_inventory,
    devices_satisfy,
    filter_by_predicates,
    norm_value,
    open_value,
    parse_device_spec,
    parse_expression,
    predicate_matches,
    search_stations,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _attr(code: str, value: str, *, date_to: Optional[str] = None) -> dict:
    return {
        "code": code,
        "value": value,
        "date_from": "2019-01-01T00:00:00",
        "date_to": date_to,
    }


def _station(
    sid: int,
    marker: str,
    name: str,
    *,
    in_epos: Optional[str] = None,
    domes: Optional[str] = None,
    extra: Optional[List[dict]] = None,
) -> dict:
    attrs: List[dict] = [
        _attr("marker", marker),
        _attr("name", name),
        _attr("subtype", "GPS stöð"),
    ]
    if in_epos is not None:
        attrs.append(_attr("in_network_epos", in_epos))
    if domes is not None:
        attrs.append(_attr("iers_domes_number", domes))
    attrs.extend(extra or [])
    return {
        "id_entity": sid,
        "code_entity_subtype": "geophysical",
        "attributes": attrs,
    }


def _device(
    did: int,
    subtype: str,
    model: Optional[str],
    serial: str = "123",
) -> dict:
    attrs: List[dict] = [
        _attr("serial_number", serial),
        _attr("status", "virkt"),
        _attr("date_start", "2020-01-01T00:00:00"),
    ]
    if model is not None:
        attrs.append(_attr("model", model))
    return {
        "id_entity": did,
        "code_entity_subtype": subtype,
        "attributes": attrs,
    }


class FakeClient:
    """Fake TOSClient — bulk listing + per-entity history."""

    def __init__(
        self,
        stations: List[dict],
        devices_by_station: Optional[Dict[int, List[dict]]] = None,
    ):
        self._stations = stations
        self._devices = devices_by_station or {}

    def list_stations(self, domain: str = "geophysical") -> List[dict]:
        return self._stations

    def get_entity_history(self, id_entity: int) -> Optional[dict]:
        # Station → children_connections (open joins only needed by engine)
        if id_entity in self._devices:
            conns = [
                {
                    "id_entity_child": d["id_entity"],
                    "id_entity_connection": 9000 + d["id_entity"],
                    "time_from": "2020-01-01T00:00:00",
                    "time_to": None,
                }
                for d in self._devices[id_entity]
            ]
            return {
                "id_entity": id_entity,
                "children_connections": conns,
                "attributes": [],
            }
        # Device entities: match by id across all stations
        for devices in self._devices.values():
            for d in devices:
                if d["id_entity"] == id_entity:
                    return d
        return None


# ---------------------------------------------------------------------------
# Value normalization
# ---------------------------------------------------------------------------


class TestNormValue:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("true", "true"),
            ("TRUE", "true"),
            ("Já", "true"),  # Icelandic yes
            ("já", "true"),
            ("yes", "true"),
            ("1", "true"),
            ("false", "false"),
            ("Nei", "false"),
            ("no", "false"),
            ("0", "false"),
            ("  Igneous  ", "igneous"),
            ("GPS stöð", "gps stöð"),
            (63.42, "63.42"),
        ],
    )
    def test_normalization(self, raw, expected):
        assert norm_value(raw) == expected


# ---------------------------------------------------------------------------
# Expression parsing
# ---------------------------------------------------------------------------


class TestParseExpression:
    def test_equality(self):
        pred = parse_expression("in_network_epos = true")
        assert pred == Predicate("in_network_epos", "=", "true")

    def test_inequality(self):
        pred = parse_expression("in_network_epos != true")
        assert pred.op == "!="

    def test_substring(self):
        pred = parse_expression("marker ~ ve")
        assert pred == Predicate("marker", "~", "ve")

    def test_substring_negated(self):
        pred = parse_expression("marker !~ ve")
        assert pred.op == "!~"

    def test_no_whitespace(self):
        pred = parse_expression("bedrock_type=igneous")
        assert pred == Predicate("bedrock_type", "=", "igneous")

    def test_value_with_spaces(self):
        pred = parse_expression("subtype = GPS stöð")
        assert pred.value == "GPS stöð"

    def test_missing_operator_raises(self):
        with pytest.raises(ValueError, match="cannot parse"):
            parse_expression("in_network_epos true")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_expression("")

    def test_code_normalized_lower(self):
        pred = parse_expression("In_Network_EPOS = true")
        assert pred.code == "in_network_epos"


# ---------------------------------------------------------------------------
# open_value + predicate matching
# ---------------------------------------------------------------------------


class TestOpenValue:
    def test_returns_open_period(self):
        st = _station(1, "a", "A", extra=[_attr("note", "current")])
        assert open_value(st, "note") == "current"

    def test_skips_closed_period(self):
        st = _station(
            1, "a", "A", extra=[_attr("note", "old", date_to="2020-01-01T00:00:00")]
        )
        assert open_value(st, "note") is None

    def test_prefers_open_over_closed(self):
        st = _station(
            1,
            "a",
            "A",
            extra=[
                _attr("note", "old", date_to="2020-01-01T00:00:00"),
                _attr("note", "new"),
            ],
        )
        assert open_value(st, "note") == "new"

    def test_absent_code(self):
        st = _station(1, "a", "A")
        assert open_value(st, "bedrock_type") is None


class TestPredicateMatches:
    def test_epos_true_matches(self):
        st = _station(1, "a", "A", in_epos="true")
        assert predicate_matches(st, Predicate("in_network_epos", "=", "true"))

    def test_epos_ja_matches_true(self):
        st = _station(1, "a", "A", in_epos="Já")
        assert predicate_matches(st, Predicate("in_network_epos", "=", "true"))

    def test_epos_absent_counts_as_not_true(self):
        st = _station(1, "a", "A")  # no in_network_epos at all
        assert predicate_matches(st, Predicate("in_network_epos", "!=", "true"))
        assert not predicate_matches(st, Predicate("in_network_epos", "=", "true"))

    def test_null_presence(self):
        st = _station(1, "a", "A", domes="10217M001")
        assert predicate_matches(st, Predicate("iers_domes_number", "!=", "null"))
        assert not predicate_matches(st, Predicate("iers_domes_number", "=", "null"))

    def test_null_absence(self):
        st = _station(1, "a", "A")
        assert predicate_matches(st, Predicate("iers_domes_number", "=", "null"))

    def test_substring(self):
        st = _station(1, "VMEY", "Vestmannaeyjar")
        assert predicate_matches(st, Predicate("marker", "~", "vm"))
        assert predicate_matches(st, Predicate("name", "~", "manna"))
        assert not predicate_matches(st, Predicate("marker", "~", "xx"))

    def test_substring_case_insensitive(self):
        st = _station(1, "VMEY", "Vestmannaeyjar")
        assert predicate_matches(st, Predicate("name", "~", "VESTMANNA"))

    def test_substring_negated_on_absent(self):
        st = _station(1, "a", "A")
        assert predicate_matches(st, Predicate("name", "!~", "ve"))

    def test_closed_period_ignored(self):
        # EPOS flag closed in the past → station is NOT currently in EPOS
        st = _station(1, "a", "A")
        st["attributes"].append(
            _attr("in_network_epos", "true", date_to="2023-10-23T00:00:00")
        )
        assert not predicate_matches(st, Predicate("in_network_epos", "=", "true"))

    def test_filter_by_predicates_ands(self):
        fleet = [
            _station(1, "aa", "AA", in_epos="true", domes="10217M001"),
            _station(2, "bb", "BB", in_epos="true"),
            _station(3, "cc", "CC", in_epos="false"),
        ]
        preds = [
            Predicate("in_network_epos", "=", "true"),
            Predicate("iers_domes_number", "!=", "null"),
        ]
        out = filter_by_predicates(fleet, preds)
        assert [open_value(s, "marker") for s in out] == ["aa"]


# ---------------------------------------------------------------------------
# Device specs
# ---------------------------------------------------------------------------


class TestParseDeviceSpec:
    def test_type_and_model(self):
        spec = parse_device_spec("receiver:polarx5")
        assert spec == DeviceSpec(
            subtype="gnss_receiver", model="polarx5", negate=False
        )

    def test_bare_model(self):
        spec = parse_device_spec("teltonika")
        assert spec.subtype is None
        assert spec.model == "teltonika"

    def test_any_model(self):
        spec = parse_device_spec("router:any")
        assert spec == DeviceSpec(subtype="router", model=None, negate=False)

    def test_wildcard_star(self):
        spec = parse_device_spec("sim:*")
        assert spec.subtype == "sim_card"
        assert spec.model is None

    def test_case_insensitive_type(self):
        spec = parse_device_spec("ANTENNA:SEPCHOKE")
        assert spec.subtype == "antenna"
        assert spec.model == "sepchoke"

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="unknown device type"):
            parse_device_spec("fluxcapacitor:delorean")

    def test_negate_flag(self):
        spec = parse_device_spec("receiver:any", negate=True)
        assert spec.negate is True


class TestDevicesSatisfy:
    DEVICES = [
        {"subtype": "gnss_receiver", "model": "SEPT POLARX5", "serial": "1"},
        {"subtype": "router", "model": "Teltonika RUT240", "serial": "2"},
        {"subtype": "sim_card", "model": None, "serial": "3"},
    ]

    def test_has_receiver_model(self):
        spec = parse_device_spec("receiver:polarx5")
        assert devices_satisfy(self.DEVICES, [spec], [])

    def test_lacks_other_model(self):
        spec = parse_device_spec("receiver:netr9")
        assert not devices_satisfy(self.DEVICES, [spec], [])

    def test_no_model_on_sim(self):
        # sim_card entities carry no model attribute — a model predicate
        # must not match them, but a type-only spec must.
        assert not devices_satisfy(
            self.DEVICES, [parse_device_spec("sim:whatever")], []
        )
        assert devices_satisfy(self.DEVICES, [parse_device_spec("sim:any")], [])

    def test_must_not(self):
        assert not devices_satisfy(
            self.DEVICES, [], [parse_device_spec("router:any", negate=True)]
        )

    def test_no_receiver(self):
        assert not devices_satisfy(
            self.DEVICES, [], [parse_device_spec("receiver:any", negate=True)]
        )
        others = self.DEVICES[1:]
        assert devices_satisfy(
            others, [], [parse_device_spec("receiver:any", negate=True)]
        )

    def test_and_combination(self):
        must = [parse_device_spec("router:teltonika"), parse_device_spec("sim:any")]
        assert devices_satisfy(self.DEVICES, must, [])


def _attr_meta(code: str, value: str, **meta) -> dict:
    """Attribute row carrying the TOS metadata fields the bulk listing has."""
    row = _attr(code, value)
    row.update(
        {
            "attribute_datatype_code": "text",
            "name_is": {"continuity": "Samfella"}.get(code, code.title()),
            "description_en": None,
            "python_constraint": ".*",
        }
    )
    row.update(meta)
    return row


# ---------------------------------------------------------------------------
# Attribute discovery (—-attribute-list / --allowed-values)
# ---------------------------------------------------------------------------


class TestAttributeInventory:
    def _fleet(self):
        return [
            {
                "id_entity": 1,
                "attributes": [
                    _attr_meta("continuity", "continuous"),
                    _attr_meta("marker", "aaa"),
                ],
            },
            {
                "id_entity": 2,
                "attributes": [
                    _attr_meta("continuity", "continuous"),
                    _attr_meta("continuity", "samfelld", date_to="2020-01-01T00:00:00"),
                    _attr_meta("marker", "bbb"),
                ],
            },
            {"id_entity": 3, "attributes": [_attr_meta("marker", "ccc")]},
        ]

    def test_counts_distinct_stations_per_code(self):
        inv = attribute_inventory(self._fleet())
        by_code = {i.code: i for i in inv}
        assert by_code["marker"].station_count == 3
        assert by_code["continuity"].station_count == 2

    def test_values_count_stations_not_periods(self):
        # Station 2 carries continuous (open) AND a closed samfelld — both
        # observed; 'continuous' still counts 2 distinct stations, not 3 rows.
        inv = attribute_inventory(self._fleet())
        cont = next(i for i in inv if i.code == "continuity")
        assert dict(cont.values)["continuous"] == 2
        assert dict(cont.values)["samfelld"] == 1

    def test_sorted_by_station_count_then_code(self):
        inv = attribute_inventory(self._fleet())
        assert [i.code for i in inv] == ["marker", "continuity"]

    def test_single_code_filter(self):
        inv = attribute_inventory(self._fleet(), code="continuity")
        assert len(inv) == 1 and inv[0].code == "continuity"
        assert attribute_inventory(self._fleet(), code="nope") == []

    def test_metadata_carried_through(self):
        inv = attribute_inventory(self._fleet(), code="continuity")
        assert inv[0].name_is == "Samfella"
        assert inv[0].datatype == "text"
        assert inv[0].constraint == ".*"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestSearchStations:
    def _fleet(self):
        return [
            _station(100, "veym", "Vestmannaeyjar", in_epos="true", domes="10217M001"),
            _station(101, "rhof", "Raufarhöfn", in_epos="true"),
            _station(102, "krac", "Krýsuvík", in_epos="false"),
            _station(103, "hhhh", "Hveravellir"),  # no epos attr
        ]

    def _devices(self):
        return {
            100: [
                _device(1, "gnss_receiver", "SEPT POLARX5"),
                _device(2, "router", "Teltonika RUT240"),
            ],
            101: [_device(3, "gnss_receiver", "TRIMBLE NETR9")],
            102: [_device(4, "antenna", "TRM57971.00")],
            103: [],
        }

    def test_attribute_only_no_walk(self):
        client = FakeClient(self._fleet())
        result = search_stations(client, [Predicate("in_network_epos", "=", "true")])
        assert result.device_filters_active is False
        assert [open_value(s, "marker") for s in result.stations] == ["rhof", "veym"]

    def test_device_filter_positive(self):
        client = FakeClient(self._fleet(), self._devices())
        result = search_stations(
            client,
            [Predicate("in_network_epos", "=", "true")],
            device_must=[parse_device_spec("receiver:polarx5")],
        )
        assert [open_value(s, "marker") for s in result.stations] == ["veym"]

    def test_device_filter_negated(self):
        client = FakeClient(self._fleet(), self._devices())
        result = search_stations(
            client,
            [],
            device_must_not=[parse_device_spec("receiver:any", negate=True)],
        )
        # krac (antenna only) + hhhh (nothing) — walk covers all stations
        # because no attribute predicate narrowed the set first.
        markers = [open_value(s, "marker") for s in result.stations]
        assert markers == ["hhhh", "krac"]

    def test_walk_only_survivors(self):
        client = FakeClient(self._fleet(), self._devices())
        result = search_stations(
            client,
            [Predicate("in_network_epos", "=", "true")],
            device_must_not=[parse_device_spec("router:any", negate=True)],
        )
        # Only rhof + veym were walked (epos=true); veym has a router.
        assert [open_value(s, "marker") for s in result.stations] == ["rhof"]
        assert set(result.devices_by_id) == {100, 101}

    def test_no_criteria_returns_all_sorted(self):
        client = FakeClient(self._fleet())
        result = search_stations(client, [])
        markers = [open_value(s, "marker") for s in result.stations]
        assert markers == sorted(markers)
        assert len(markers) == 4

    def test_attribute_codes_dedupe_predicate_and_show(self):
        client = FakeClient(self._fleet())
        result = search_stations(
            client,
            [Predicate("in_network_epos", "=", "true")],
            show_codes=["iers_domes_number", "in_network_epos"],
        )
        assert result.attribute_codes == ["in_network_epos", "iers_domes_number"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_cli(argv: List[str], fleet, devices=None, capsys=None):
    from tostools.tos import _search_main

    fake = FakeClient(fleet, devices)
    with patch("tostools.api.tos_client.TOSClient", return_value=fake):
        rc = _search_main(argv)
    out = ""
    if capsys:
        captured = capsys.readouterr()
        out = captured.out + captured.err
    return rc, out


class TestSearchCli:
    def _fleet(self):
        return [
            _station(100, "VMEY", "Vestmannaeyjar", in_epos="true", domes="10217M001"),
            _station(101, "RHOF", "Raufarhöfn", in_epos="true"),
            _station(102, "KRAC", "Krýsuvík", in_epos="false"),
        ]

    def test_dispatch_through_main(self):
        from tostools.tos import main

        with patch("tostools.tos._search_main", return_value=0) as spy:
            rc = main(["search", "--epos"])
        assert rc == 0
        spy.assert_called_once_with(["--epos"])

    def test_epos_sugar_table(self, capsys):
        rc, out = _run_cli(["--epos"], self._fleet(), capsys=capsys)
        assert rc == 0
        assert "2 station(s) match" in out
        assert "VMEY" in out and "RHOF" in out
        assert "KRAC" not in out
        # predicate code becomes a column
        assert "IN_NETWORK_EPOS" in out

    def test_no_epos_markers_only(self, capsys):
        rc, out = _run_cli(
            ["--no-epos", "--markers-only"], self._fleet(), capsys=capsys
        )
        assert rc == 0
        assert out.split() == ["KRAC"]

    def test_expression_json(self, capsys):
        rc, out = _run_cli(
            ["in_network_epos = true", "--json"], self._fleet(), capsys=capsys
        )
        assert rc == 0
        payload = json.loads(out)
        assert payload["count"] == 2
        assert payload["criteria"]["attributes"] == ["in_network_epos = true"]
        markers = {s["marker"] for s in payload["stations"]}
        assert markers == {"VMEY", "RHOF"}
        # show codes/predicate codes surfaced per station
        assert payload["stations"][0]["attributes"]["in_network_epos"] == "true"

    def test_device_filter_cli(self, capsys):
        devices = {
            100: [_device(1, "gnss_receiver", "SEPT POLARX5")],
            101: [_device(2, "gnss_receiver", "TRIMBLE NETR9")],
            102: [_device(3, "antenna", "TRM57971.00")],
        }
        rc, out = _run_cli(
            ["--epos", "--receiver", "polarx5", "--markers-only"],
            self._fleet(),
            devices=devices,
            capsys=capsys,
        )
        assert rc == 0
        assert out.split() == ["VMEY"]

    def test_bad_expression_usage_error(self, capsys):
        rc, _ = _run_cli(["nonsense expression here"], self._fleet(), capsys=capsys)
        assert rc == 2

    def test_bad_device_type_usage_error(self, capsys):
        rc, _ = _run_cli(
            ["--device", "warpcore:dilithium"], self._fleet(), capsys=capsys
        )
        assert rc == 2

    def test_limit(self, capsys):
        rc, out = _run_cli(
            ["--epos", "--markers-only", "--limit", "1"], self._fleet(), capsys=capsys
        )
        assert rc == 0
        assert out.split() == ["RHOF"]  # sorted by marker: rhof < veym

    def test_show_extra_column(self, capsys):
        rc, out = _run_cli(
            ["--epos", "--show", "iers_domes_number"], self._fleet(), capsys=capsys
        )
        assert rc == 0
        assert "IERS_DOMES_NUMBER" in out
        assert "10217M001" in out

    def test_zero_results_is_success(self, capsys):
        rc, out = _run_cli(["marker = zzzz"], self._fleet(), capsys=capsys)
        assert rc == 0
        assert "0 station(s) match" in out

    def test_no_criteria_lists_all(self, capsys):
        rc, out = _run_cli(["--markers-only"], self._fleet(), capsys=capsys)
        assert rc == 0
        assert out.split() == ["KRAC", "RHOF", "VMEY"]


class TestDiscoveryCli:
    def _fleet(self):
        return [
            {
                "id_entity": 1,
                "attributes": [
                    _attr_meta("marker", "aaa"),
                    _attr_meta("continuity", "continuous"),
                ],
            },
            {
                "id_entity": 2,
                "attributes": [
                    _attr_meta("marker", "bbb"),
                    _attr_meta("continuity", "campaign"),
                ],
            },
        ]

    def test_attribute_list(self, capsys):
        rc, out = _run_cli(["--attribute-list"], self._fleet(), capsys=capsys)
        assert rc == 0
        assert "marker" in out and "continuity" in out
        assert "2 attribute code(s) observed" in out
        # station counts rendered
        assert "Samfella" in out

    def test_allowed_values(self, capsys):
        rc, out = _run_cli(
            ["--attribute", "continuity", "--allowed-values"],
            self._fleet(),
            capsys=capsys,
        )
        assert rc == 0
        assert "Samfella" in out
        assert "continuous" in out and "campaign" in out
        assert "constraint" in out

    def test_allowed_values_without_attribute_is_usage_error(self, capsys):
        rc, _ = _run_cli(["--allowed-values"], self._fleet(), capsys=capsys)
        assert rc == 2

    def test_unknown_attribute_is_error(self, capsys):
        rc, out = _run_cli(
            ["--attribute", "warpfield", "--allowed-values"],
            self._fleet(),
            capsys=capsys,
        )
        assert rc == 1
        assert "never observed" in out  # stderr message


class TestActiveGpsFlag:
    def _fleet(self):
        def st(sid, marker, **extra_codes):
            attrs = [
                _attr("marker", marker),
                _attr("name", marker),
                _attr("subtype", "GPS stöð"),
            ]
            for code, val in extra_codes.items():
                attrs.append(_attr(code, val))
            return {"id_entity": sid, "attributes": attrs}

        return [
            st(1, "good", continuity="continuous", geological_characteristic="bedrock"),
            st(2, "ended", continuity="continuous", date_end="2017-01-01 00:00"),
            st(3, "ice", continuity="continuous", geological_characteristic="ice"),
            st(
                4,
                "campaign",
                continuity="campaign",
                geological_characteristic="bedrock",
            ),
            st(5, "nofill", geological_characteristic="bedrock"),  # no continuity
            st(6, "sil", continuity="continuous"),  # SIL: overwrite subtype below
        ]

    def test_flag_keeps_only_operational_gps(self, capsys):
        fleet = self._fleet()
        fleet[5]["attributes"][2]["value"] = "SIL stöð"  # station 6 is SIL
        rc, out = _run_cli(["--active-gps", "--markers-only"], fleet, capsys=capsys)
        assert rc == 0
        assert out.split() == ["GOOD"]

    def test_flag_predicates_visible_in_criteria(self, capsys):
        rc, out = _run_cli(["--active-gps", "--json"], self._fleet(), capsys=capsys)
        assert rc == 0
        payload = json.loads(out)
        assert payload["criteria"]["attributes"] == [
            "subtype = GPS stöð",
            "date_end = null",
            "geological_characteristic != ice",
            "continuity = continuous",
        ]

    def test_flag_composes_with_expression(self, capsys):
        fleet = self._fleet()
        fleet[0]["attributes"].append(_attr("in_network_epos", "true"))
        rc, out = _run_cli(
            ["--active-gps", "--epos", "--markers-only"], fleet, capsys=capsys
        )
        assert rc == 0
        assert out.split() == ["GOOD"]
