"""Unit + CLI tests for ``tos search --selectors``.

The contract under test is that discovery output is *usable*: every line
starts with a selector spelled exactly as ``tos search`` parses it, so what
you read can be pasted into the next command without editing.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tostools import search_selectors as sel
from tostools.search import DEVICE_SUBTYPE_ALIASES, parse_selector


class TestResolveTopic:
    def test_none_is_the_index(self):
        assert sel.resolve_topic(None) is None
        assert sel.resolve_topic("") is None
        assert sel.resolve_topic("   ") is None

    @pytest.mark.parametrize("topic", ["station", "subtypes", "all"])
    def test_reserved_topics(self, topic):
        assert sel.resolve_topic(topic) == topic

    def test_alias_resolves_to_canonical(self):
        assert sel.resolve_topic("receiver") == "gnss_receiver"
        assert sel.resolve_topic("sim") == "sim_card"

    def test_case_insensitive(self):
        assert sel.resolve_topic("Receiver") == "gnss_receiver"

    def test_unknown_lists_valid_choices(self):
        with pytest.raises(ValueError, match="unknown --selectors topic"):
            sel.resolve_topic("widget")
        try:
            sel.resolve_topic("widget")
        except ValueError as exc:
            assert "receiver" in str(exc) and "station" in str(exc)


class TestSubtypeHelpers:
    def test_canonical_subtypes_are_deduped(self):
        subs = sel.canonical_subtypes()
        assert len(subs) == len(set(subs))
        assert "gnss_receiver" in subs
        assert set(subs) == set(DEVICE_SUBTYPE_ALIASES.values())

    def test_aliases_shortest_first(self):
        assert sel.aliases_for("gnss_receiver")[0] == "receiver"

    def test_subtype_with_single_alias(self):
        assert sel.aliases_for("antenna") == ["antenna"]


class TestRoundTrip:
    """Everything emitted must parse back — the whole point of the flag."""

    def test_station_selectors_parse_as_station(self):
        for entry in sel.station_group().entries:
            namespace, code = parse_selector(entry.selector)
            assert namespace is None
            assert code == entry.selector

    def test_device_selectors_parse_to_their_subtype(self):
        for subtype in ("gnss_receiver", "antenna", "radome", "monument"):
            group = sel.device_group(subtype)
            assert group.entries, f"catalog should classify {subtype}"
            for entry in group.entries:
                namespace, _ = parse_selector(entry.selector)
                assert namespace == subtype

    def test_subtype_namespaces_parse(self):
        for entry in sel.subtypes_group().entries:
            # 'receiver.' is a prefix, so complete it before parsing.
            namespace, code = parse_selector(entry.selector + "model")
            assert namespace is not None
            assert code == "model"


class TestCatalogSource:
    def test_receiver_has_the_firmware_pair(self):
        codes = sel.catalog_device_codes("gnss_receiver")
        assert "firmware_version" in codes
        assert "software_version" in codes

    def test_station_codes_include_domes(self):
        assert "iers_domes_number" in sel.catalog_station_codes()

    def test_telemetry_subtypes_are_empty_in_the_catalog(self):
        """Documents the gap --observed exists to fill."""
        for subtype in ("sim_card", "router", "modem_gsm"):
            assert sel.catalog_device_codes(subtype) == {}

    def test_gap_group_carries_the_remedy(self):
        group = sel.device_group("sim_card")
        assert group.entries == []
        assert "--observed" in (group.note or "")


class TestObservedSource:
    def _devices(self):
        return {
            1: [
                {
                    "subtype": "sim_card",
                    "attributes": [
                        {"code": "phone_number", "value": "8320883"},
                        {"code": "provider", "value": "Síminn"},
                    ],
                },
                {
                    "subtype": "gnss_receiver",
                    "attributes": [{"code": "firmware_version", "value": "5.7.0"}],
                },
            ],
            2: [
                {
                    "subtype": "sim_card",
                    "attributes": [{"code": "phone_number", "value": "8581708"}],
                }
            ],
        }

    def test_counts_devices_per_code(self):
        counts = sel.observed_device_codes(self._devices(), "sim_card")
        assert counts["phone_number"] == 2
        assert counts["provider"] == 1

    def test_does_not_leak_across_subtypes(self):
        counts = sel.observed_device_codes(self._devices(), "sim_card")
        assert "firmware_version" not in counts

    def test_observed_subtype_counts(self):
        assert sel.observed_subtypes(self._devices()) == {
            "sim_card": 2,
            "gnss_receiver": 1,
        }

    def test_station_codes_counted_once_per_station(self):
        stations = [
            {
                "attributes": [
                    {"code": "marker"},
                    {"code": "marker"},  # two periods, one station
                    {"code": "name"},
                ]
            }
        ]
        assert sel.observed_station_codes(stations) == {"marker": 1, "name": 1}

    def test_observed_fills_a_catalog_gap(self):
        group = sel.device_group(
            "sim_card", observed=sel.observed_device_codes(self._devices(), "sim_card")
        )
        selectors = [e.selector for e in group.entries]
        assert "sim.phone_number" in selectors
        assert all(e.sources == ("observed",) for e in group.entries)

    def test_sources_tagged_when_both_agree(self):
        observed = {"firmware_version": 100}
        group = sel.device_group("gnss_receiver", observed=observed)
        fw = next(e for e in group.entries if e.selector == "receiver.firmware_version")
        assert fw.sources == ("catalog", "observed")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run(argv, capsys):
    from tostools.tos import _search_main

    rc = _search_main(argv)
    cap = capsys.readouterr()
    return rc, cap.out + cap.err


class TestSelectorsCli:
    def test_bare_prints_the_index_not_everything(self, capsys):
        rc, out = _run(["--selectors"], capsys)
        assert rc == 0
        assert "ask for one of" in out
        # The index must NOT dump the attributes themselves.
        assert "receiver.firmware_version" not in out

    def test_index_lists_every_subtype(self, capsys):
        rc, out = _run(["--selectors"], capsys)
        for alias in ("station", "subtypes", "receiver", "antenna", "sim", "all"):
            assert alias in out

    def test_station_topic(self, capsys):
        rc, out = _run(["--selectors", "station"], capsys)
        assert rc == 0
        assert "iers_domes_number" in out
        assert "receiver." not in out, "station topic must not leak device codes"

    def test_receiver_topic_emits_prefixed_selectors(self, capsys):
        rc, out = _run(["--selectors", "receiver"], capsys)
        assert rc == 0
        assert "receiver.firmware_version" in out

    def test_unknown_topic_exits_2(self, capsys):
        rc, out = _run(["--selectors", "widget"], capsys)
        assert rc == 2
        assert "unknown --selectors topic" in out

    def test_json_emits_bare_selector_array(self, capsys):
        rc, out = _run(["--selectors", "receiver", "--json"], capsys)
        assert rc == 0
        payload = json.loads(out)
        assert payload["topic"] == "gnss_receiver"
        selectors = payload["groups"][0]["selectors"]
        assert "receiver.firmware_version" in selectors
        for s in selectors:
            assert parse_selector(s)[0] == "gnss_receiver"

    def test_all_topic_has_a_group_per_subtype(self, capsys):
        rc, out = _run(["--selectors", "all", "--json"], capsys)
        assert rc == 0
        titles = [g["title"] for g in json.loads(out)["groups"]]
        assert any("station attributes" in t for t in titles)
        assert any("device subtypes" in t for t in titles)
        assert any("gnss_receiver attributes" in t for t in titles)

    def test_selectors_needs_no_network(self, capsys):
        """Catalog-driven: no --observed means no client is constructed."""

        class Exploding:
            def __init__(self, *a, **k):
                raise AssertionError("--selectors must not hit TOS")

        with patch("tostools.api.tos_client.TOSClient", Exploding):
            rc, out = _run(["--selectors", "receiver"], capsys)
        assert rc == 0
        assert "receiver.firmware_version" in out

    def test_profile_filters_and_marks_mandatory(self, capsys):
        from tostools.search_selectors import gps_profile
        from tostools.tos import _search_main

        _search_main(["--selectors", "receiver", "--json"], profile=gps_profile())
        payload = json.loads(capsys.readouterr().out)
        entries = payload["groups"][0]["entries"]
        codes = {e["selector"] for e in entries}
        assert "receiver.firmware_version" in codes
        assert "receiver.access_taeki_id" not in codes, "gps_relevance=no must go"
        fw = next(e for e in entries if e["selector"] == "receiver.firmware_version")
        assert fw["mandatory"] is True

    def test_profile_lists_mandatory_first(self, capsys):
        from tostools.search_selectors import gps_profile
        from tostools.tos import _search_main

        _search_main(["--selectors", "receiver", "--json"], profile=gps_profile())
        entries = json.loads(capsys.readouterr().out)["groups"][0]["entries"]
        flags = [e["mandatory"] for e in entries]
        assert flags == sorted(flags, reverse=True), "mandatory block must lead"

    def test_output_first_token_is_a_usable_selector(self, capsys):
        """Copy-paste contract: line 1 token parses, labels never lead."""
        rc, out = _run(["--selectors", "receiver"], capsys)
        assert rc == 0
        rows = [ln for ln in out.splitlines() if ln.startswith("  ") and "." in ln]
        assert rows
        for line in rows:
            token = line.split()[0]
            namespace, _ = parse_selector(token)
            assert namespace == "gnss_receiver"
