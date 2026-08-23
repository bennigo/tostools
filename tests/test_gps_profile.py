"""The GPS profile — what makes ``tosGPS search`` a different tool.

``tos`` is the unconstrained CLI; ``tosGPS`` is the same engine narrowed to
one discipline. Two constraints define the difference and both are tested
here: the station subtype is pinned, and a selector the catalog does not
mark ``gps_relevance: yes`` is refused rather than quietly answered.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tostools.search_selectors import ANY_DEVICE, gps_profile


@pytest.fixture(scope="module")
def profile():
    return gps_profile()


class TestProfileShape:
    def test_pins_the_gps_subtype(self, profile):
        assert profile.name == "GPS"
        assert profile.subtype == "GPS stöð"

    def test_membership_is_a_strict_subset(self, profile):
        from tostools.search_selectors import catalog_station_codes

        assert 0 < len(profile.station) < len(catalog_station_codes())

    def test_known_gps_attributes_are_in(self, profile):
        assert profile.allows(None, "iers_domes_number")
        assert profile.allows("gnss_receiver", "firmware_version")
        assert profile.allows("gnss_receiver", "software_version")
        assert profile.allows("antenna", "serial_number")

    def test_non_gps_attribute_is_out(self, profile):
        assert not profile.allows("gnss_receiver", "access_taeki_id")

    def test_mandatory_reflects_gps_required_for(self, profile):
        assert profile.mandatory("gnss_receiver", "serial_number")
        assert profile.mandatory("gnss_receiver", "firmware_version")
        assert not profile.mandatory("gnss_receiver", "cable_length")

    def test_mandatory_is_per_subtype(self, profile):
        """A code can be required on one subtype and optional on another."""
        per_subtype = {
            s: profile.mandatory(s, "serial_number")
            for s in profile.subtypes()
            if profile.allows(s, "serial_number")
        }
        assert per_subtype, "serial_number should exist on several subtypes"
        assert any(per_subtype.values())

    def test_mandatory_implies_allowed(self, profile):
        """gps_required_for must never appear without gps_relevance=yes."""
        for subtype, codes in profile.devices.items():
            for code, required in codes.items():
                if required:
                    assert profile.allows(subtype, code)

    def test_any_device_namespace_spans_subtypes(self, profile):
        assert profile.allows(ANY_DEVICE, "firmware_version")
        assert not profile.allows(ANY_DEVICE, "access_taeki_id")

    def test_curated_subtypes_are_the_catalog_four(self, profile):
        # The telemetry subtypes carry no GPS-relevant attributes, so the
        # profile should not advertise them.
        assert set(profile.subtypes()) == {
            "gnss_receiver",
            "antenna",
            "radome",
            "monument",
        }


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def _run(argv, capsys, profile=None):
    from tostools.tos import _search_main

    rc = _search_main(argv, profile=profile)
    cap = capsys.readouterr()
    return rc, cap.out + cap.err


class TestProfileGate:
    def test_non_gps_selector_is_refused(self, capsys, profile):
        rc, out = _run(["receiver.access_taeki_id = 1"], capsys, profile)
        assert rc == 2
        assert "is not a GPS attribute" in out

    def test_refusal_suggests_the_short_alias(self, capsys, profile):
        rc, out = _run(["receiver.access_taeki_id = 1"], capsys, profile)
        assert "--selectors receiver" in out
        assert "--selectors gnss_receiver" not in out

    def test_refusal_points_at_plain_tos(self, capsys, profile):
        rc, out = _run(["receiver.access_taeki_id = 1"], capsys, profile)
        assert "tos search" in out

    def test_non_gps_selector_in_show_is_refused(self, capsys, profile):
        rc, out = _run(["--show", "receiver.access_taeki_id"], capsys, profile)
        assert rc == 2
        assert "is not a GPS attribute" in out

    def test_same_selector_is_fine_without_a_profile(self, capsys):
        """The gate is the profile's, not the parser's."""

        class Empty:
            def list_stations(self, domain="geophysical"):
                return []

        with patch("tostools.api.tos_client.TOSClient", return_value=Empty()):
            rc, out = _run(["receiver.access_taeki_id = 1", "--markers-only"], capsys)
        assert rc == 0
        assert "is not a GPS attribute" not in out

    def test_diagnostics_name_the_typed_command(self, capsys, profile):
        rc, out = _run(["receiver.access_taeki_id = 1"], capsys, profile)
        assert out.startswith("tosGPS search:")


class TestSubtypePin:
    def test_conflicting_subtype_is_refused(self, capsys, profile):
        rc, out = _run(["subtype = SIL stöð"], capsys, profile)
        assert rc == 2
        assert "pinned to" in out

    def test_subtype_all_is_refused(self, capsys, profile):
        """'subtype = all' lifts the scope — exactly what a profile forbids."""
        rc, out = _run(["subtype = all"], capsys, profile)
        assert rc == 2

    def test_redundant_matching_subtype_is_allowed(self, capsys, profile):
        class Empty:
            def list_stations(self, domain="geophysical"):
                return []

        with patch("tostools.api.tos_client.TOSClient", return_value=Empty()):
            rc, out = _run(["subtype = GPS stöð", "--markers-only"], capsys, profile)
        assert rc == 0

    def test_pin_is_applied_when_unspecified(self, capsys, profile):
        class Empty:
            def list_stations(self, domain="geophysical"):
                return []

        with patch("tostools.api.tos_client.TOSClient", return_value=Empty()):
            rc, out = _run(["--json"], capsys, profile)
        assert rc == 0
        crit = json.loads(out)["criteria"]["attributes"]
        assert "subtype = GPS stöð" in crit


class TestTosGpsDelegation:
    """What `tosGPS` forwards to the shared engine, and how.

    Asymmetric on purpose: `search` is profiled because `tos search` is
    unconstrained, while `audit` is a plain alias because the audit is
    already GPS-only by construction (audit_missing_attributes skips every
    gps_relevance != 'yes' code). Applying a profile there would be
    redundant, and `tos audit` must stay byte-identical — gps-tos-corrections
    records 270 `tos audit apply` invocations as procedure.
    """

    def _main(self, argv):
        import tostools.tosGPS as tosgps

        with patch.object(tosgps.sys, "argv", ["tosGPS", *argv]):
            return tosgps.main()

    def test_search_is_delegated_with_the_gps_profile(self):
        import tostools.tos as tos_mod

        with patch.object(tos_mod, "_search_main", return_value=0) as spy:
            assert self._main(["search", "--markers-only"]) == 0
        argv, kwargs = spy.call_args
        assert argv[0] == ["--markers-only"]
        assert kwargs["profile"].name == "GPS"

    @pytest.mark.parametrize(
        "verb,handler",
        [
            ("audit", "_audit_main"),
            ("fleet", "_fleet_main"),
            ("station", "_station_main"),
        ],
    )
    def test_plain_aliases_delegate_unprofiled(self, verb, handler):
        """Every table entry forwards verbatim — no profile, exact argv."""
        import tostools.tos as tos_mod

        with patch.object(tos_mod, handler, return_value=0) as spy:
            assert self._main([verb, "--help"]) == 0
        spy.assert_called_once_with(["--help"])

    def test_the_alias_table_excludes_search(self):
        """search is the one verb WITH unconstrained behaviour to narrow."""
        from tostools.tosGPS import _PLAIN_ALIASES

        assert "search" not in _PLAIN_ALIASES

    def test_every_alias_target_exists_on_tos(self):
        """A typo in the table would surface as AttributeError at runtime."""
        import tostools.tos as tos_mod
        from tostools.tosGPS import _PLAIN_ALIASES

        for verb, handler in _PLAIN_ALIASES.items():
            assert callable(
                getattr(tos_mod, handler, None)
            ), f"{verb} -> {handler} is not a callable on tos.py"

    def test_audit_is_delegated_with_NO_profile(self):
        import tostools.tos as tos_mod

        with patch.object(tos_mod, "_audit_main", return_value=0) as spy:
            assert self._main(["audit", "timeline", "16156"]) == 0
        spy.assert_called_once_with(["timeline", "16156"])

    def test_audit_delegates_to_the_very_same_function(self):
        """Alias, not a reimplementation — one function, one behaviour."""
        import tostools.tos as tos_mod

        seen = {}

        def _record(argv):
            seen["argv"] = argv
            return 7

        with patch.object(tos_mod, "_audit_main", _record):
            rc = self._main(["audit", "--help"])
        assert rc == 7, "tosGPS must return the exit code tos audit produced"
        assert seen["argv"] == ["--help"]

    def test_product_subcommands_are_not_intercepted(self):
        """PrintTOS/rinex/sitelog/... still reach tosGPS's own parser."""
        import tostools.tos as tos_mod

        with (
            patch.object(tos_mod, "_audit_main") as audit,
            patch.object(tos_mod, "_search_main") as search,
        ):
            with pytest.raises(SystemExit):
                self._main(["nonsense-verb"])
        audit.assert_not_called()
        search.assert_not_called()


class TestProfiledDiscovery:
    def test_station_topic_is_narrowed(self, capsys, profile):
        rc, out = _run(["--selectors", "station"], capsys, profile)
        assert rc == 0
        assert "GPS-relevant only" in out
        assert "iers_domes_number" in out

    def test_all_topic_skips_uncurated_subtypes(self, capsys, profile):
        rc, out = _run(["--selectors", "all", "--json"], capsys, profile)
        assert rc == 0
        titles = " ".join(g["title"] for g in json.loads(out)["groups"])
        assert "gnss_receiver" in titles
        assert "sim_card" not in titles, "no GPS attributes — should not appear"

    def test_uncurated_subtype_says_why_it_is_empty(self, capsys, profile):
        rc, out = _run(["--selectors", "sim"], capsys, profile)
        assert rc == 0
        assert "no GPS-relevant attributes" in out
        assert "tos search" in out


# ---------------------------------------------------------------------------
# Fleet scope — IMO stations, not the IGS reference sites
# ---------------------------------------------------------------------------


class TestImoFleetMarkers:
    """`stations.cfg` mixes the IMO fleet with global IGS reference sites.

    The reference sites have no TOS entity, so auditing one is a round-trip
    that can only report an error. The discriminator is `is_reference_site`
    — NOT `station_role = passive`, which nearly coincides but silently
    drops eight real IMO stations.
    """

    CFG = {
        "VMEY": {"station_id": "VMEY"},
        "FAFC": {"station_role": "passive", "is_reference_site": "false"},
        "ALIC": {"station_role": "passive", "is_reference_site": "true"},
        "AMC2": {"is_reference_site": "TRUE"},
    }

    def test_reference_sites_excluded(self):
        from tostools.audit_fleet_sweep import imo_fleet_markers

        assert imo_fleet_markers(self.CFG) == ["FAFC", "VMEY"]

    def test_passive_but_real_station_is_kept(self):
        """FAFC is passive AND runs a PolaRX5 — it must survive."""
        from tostools.audit_fleet_sweep import imo_fleet_markers

        assert "FAFC" in imo_fleet_markers(self.CFG)

    def test_flag_is_case_insensitive(self):
        from tostools.audit_fleet_sweep import is_reference_site

        assert is_reference_site({"is_reference_site": "TRUE"})
        assert is_reference_site({"is_reference_site": " true "})
        assert not is_reference_site({"is_reference_site": "false"})

    def test_absent_flag_means_imo(self):
        from tostools.audit_fleet_sweep import is_reference_site

        assert not is_reference_site({})

    def test_station_role_is_not_the_discriminator(self):
        """Guard against a future 'simplification' back to station_role."""
        from tostools.audit_fleet_sweep import is_reference_site

        assert not is_reference_site({"station_role": "passive"})

    def test_markers_are_uppercased_and_sorted(self):
        from tostools.audit_fleet_sweep import imo_fleet_markers

        assert imo_fleet_markers({"vmey": {}, "akur": {}}) == ["AKUR", "VMEY"]


class TestFleetDelegation:
    def test_fleet_is_delegated_with_NO_profile(self):
        import tostools.tos as tos_mod
        import tostools.tosGPS as tosgps

        with patch.object(tos_mod, "_fleet_main", return_value=0) as spy:
            with patch.object(tosgps.sys, "argv", ["tosGPS", "fleet", "status"]):
                assert tosgps.main() == 0
        spy.assert_called_once_with(["status"])
