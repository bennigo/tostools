"""Tests for `tos visit search` — fleet-wide free-text vitjun search.

Pins the cross-check behaviour the EPOS onboarding flow depends on:
`tos visit search --epos --work 'TOS reviewed' --missing` lists exactly
the stations still to onboard.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from tostools.tos import _visit_main


def _entity(marker: str, *, epos: bool = True, eid: int) -> dict:
    attrs = [
        {"code": "marker", "value": marker.lower(), "date_from": "2020-01-01", "date_to": None},
        {"code": "name", "value": f"Name {marker}", "date_from": "2020-01-01", "date_to": None},
    ]
    if epos:
        attrs.append(
            {
                "code": "in_network_epos",
                "value": "true",
                "date_from": "2020-01-01",
                "date_to": None,
            }
        )
    return {"id_entity": eid, "attributes": attrs}


def _visit(vid: int, work: str, vtype: str = "remote") -> dict:
    return {
        "id": vid,
        "work": work,
        "maintenance_type": vtype,
        "start_time": "2026-08-24T00:00:00",
    }


def _run(*argv, fleet, visits_map):
    client = MagicMock()
    client.list_maintenance_visits.side_effect = lambda eid: visits_map.get(eid, [])
    with (
        patch("tostools.search.fetch_fleet", return_value=fleet),
        patch("tostools.api.tos_client.TOSClient", return_value=client),
    ):
        rc = _visit_main(["search", *argv])
    return rc, client


def _markers_from_stdout(capsys):
    out = capsys.readouterr().out
    return [ln for ln in out.splitlines() if ln.strip()]


def test_search_epos_work_missing_lists_stations_without_match(capsys):
    fleet = [
        _entity("RHOF", epos=True, eid=1),   # onboarded
        _entity("THOC", epos=True, eid=2),   # onboarded
        _entity("HAUC", epos=True, eid=3),   # NOT onboarded
        _entity("FIM2", epos=False, eid=4),  # not EPOS — excluded by --epos
    ]
    visits = {
        1: [_visit(1, "TOS reviewed, re-rinexed to R3")],
        2: [_visit(2, "TOS reviewed, re-rinexed to R3")],
        3: [_visit(3, "firmware uppfært")],
    }
    rc, _ = _run(
        "--epos", "--work", "TOS reviewed", "--missing", "--markers-only",
        fleet=fleet, visits_map=visits,
    )
    assert rc == 0
    assert _markers_from_stdout(capsys) == ["hauc"]


def test_search_work_matches_case_insensitively(capsys):
    fleet = [_entity("RHOF", epos=False, eid=1)]
    visits = {1: [_visit(1, "TOS REVIEWED, re-rinexed")]}
    rc, _ = _run("--work", "tos reviewed", "--markers-only",
                 fleet=fleet, visits_map=visits)
    assert rc == 0
    assert _markers_from_stdout(capsys) == ["rhof"]


def test_search_type_filter_is_applied(capsys):
    fleet = [_entity("RHOF", epos=False, eid=1)]
    visits = {1: [_visit(1, "some on-site work", vtype="on_site")]}
    rc, _ = _run("--type", "remote", "--markers-only",
                 fleet=fleet, visits_map=visits)
    assert rc == 0
    assert _markers_from_stdout(capsys) == []  # no remote visit → no match


def test_search_json_reports_matched_and_missing(capsys):
    fleet = [
        _entity("RHOF", epos=True, eid=1),
        _entity("HAUC", epos=True, eid=2),
    ]
    visits = {1: [_visit(1, "TOS reviewed")]}
    rc, _ = _run("--epos", "--work", "TOS reviewed", "--json",
                 fleet=fleet, visits_map=visits)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["matched"] == 1
    assert payload["missing"] == 1
    assert payload["stations_without_match"] == ["hauc"]


def test_search_scopes_by_positional_expression(capsys):
    # A general station predicate narrows the visit search — not just --epos.
    fleet = [
        _entity("RHOF", epos=False, eid=1),
        _entity("THOC", epos=False, eid=2),
    ]
    visits = {1: [_visit(1, "TOS reviewed")], 2: [_visit(2, "TOS reviewed")]}
    rc, _ = _run("--work", "TOS reviewed", "--missing", "--markers-only",
                 "marker = thoc", fleet=fleet, visits_map=visits)
    assert rc == 0
    # THOC has the visit, so --missing with 'marker = thoc' yields nothing;
    # RHOF is excluded by the expression.
    assert _markers_from_stdout(capsys) == []


def test_search_scopes_by_sugar_flag(capsys):
    # A sugar flag is a station predicate, not a visit filter: it must
    # remove stations that fail it from scope before the visit match.
    fleet = [
        _entity("RHOF", epos=False, eid=1),
        _entity("THOC", epos=False, eid=2),
    ]
    # RHOF is continuous → passes --continuous; THOC is not.
    fleet[0]["attributes"].append(
        {"code": "continuity", "value": "continuous", "date_from": "2020-01-01", "date_to": None}
    )
    visits = {2: [_visit(1, "TOS reviewed")]}  # THOC has the visit
    rc, _ = _run("--work", "TOS reviewed", "--missing", "--continuous",
                 "--markers-only", fleet=fleet, visits_map=visits)
    assert rc == 0
    # Only RHOF (continuous) is in scope and it lacks the visit.
    assert _markers_from_stdout(capsys) == ["rhof"]


def _gps_profile():
    from tostools.search_selectors import Profile

    return Profile(
        name="GPS",
        subtype="GPS stöð",
        station={"marker": True, "name": True, "in_network_epos": True, "subtype": True, "continuity": True},
        devices={},
    )


def test_profile_pins_subtype_scope(capsys):
    # tosGPS visit search must pin subtype = GPS stöð even with no expression.
    from unittest.mock import patch

    fleet = [
        _entity("RHOF", epos=False, eid=1),
        _entity("SIL1", epos=False, eid=2),
    ]
    fleet[0]["attributes"].append(
        {"code": "subtype", "value": "GPS stöð", "date_from": "2020-01-01", "date_to": None}
    )
    fleet[1]["attributes"].append(
        {"code": "subtype", "value": "SIL stöð", "date_from": "2020-01-01", "date_to": None}
    )
    # Neither has a matching visit, so WITHOUT the pin both would be listed
    # missing; WITH the pin only RHOF (GPS) is in scope.
    client = MagicMock()
    client.list_maintenance_visits.side_effect = lambda eid: []
    from tostools.tos import _visit_main

    with (
        patch("tostools.search.fetch_fleet", return_value=fleet),
        patch("tostools.api.tos_client.TOSClient", return_value=client),
    ):
        rc = _visit_main(
            ["search", "--work", "TOS reviewed", "--missing", "--markers-only"],
            profile=_gps_profile(),
        )
    assert rc == 0
    assert _markers_from_stdout(capsys) == ["rhof"]


def test_profile_gate_refuses_foreign_attribute(capsys):
    from unittest.mock import patch

    from tostools.tos import _visit_main

    fleet = [_entity("RHOF", epos=False, eid=1)]
    client = MagicMock()
    with (
        patch("tostools.search.fetch_fleet", return_value=fleet),
        patch("tostools.api.tos_client.TOSClient", return_value=client),
    ):
        rc = _visit_main(
            ["search", "--work", "x", "meteorological_zone ~ foo"],
            profile=_gps_profile(),
        )
    assert rc == 2
    assert "not a GPS attribute" in capsys.readouterr().err
