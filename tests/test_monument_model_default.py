"""A monument's `model` gets the fleet mode, labelled as a mode.

For a monument, `model` is the mark's CONSTRUCTION TYPE and IGS site log §3.1
"Foundation" renders from it — so this suggestion is published internationally,
not held internally. Measured across 24 fleet monuments (2026-08-18):

    11  GPS stál-fjórfótur      3  steyptur stöpull
     8  (no value)              1  pinni / 1 GPS stál-staur

11 of the 16 known = 69 %. A clear mode, but ~1 in 3 known marks is something
else, which is why the provenance says so rather than presenting it as a finding.
"""

from tostools.audit_missing_attributes import _MONUMENT_MODEL_FLEET_MODE


class TestFleetMode:
    def test_value_matches_the_fleet(self):
        assert _MONUMENT_MODEL_FLEET_MODE == "GPS stál-fjórfótur"

    def test_it_is_not_a_catalog_default(self):
        # `model` also applies to receivers, antennas and radomes, where a
        # monument value would be nonsense — which is exactly why this cannot
        # live in the catalog's default_value and needs a subtype-aware branch.
        from tostools.audit_attribute_dates import load_catalog

        try:
            cat = load_catalog()
        except Exception:  # noqa: BLE001 — catalog shape varies by install
            return
        entry = (cat or {}).get("model") or {}
        assert entry.get("default_value") in (None, "", "~")


class TestSuggestionRanking:
    """Evidence order: station.info > catalog default > fleet mode."""

    def test_fleet_mode_is_the_weakest_tier(self):
        import inspect

        from tostools import audit_missing_attributes as m

        src = inspect.getsource(m._audit_entity)
        fleet_at = src.find("_MONUMENT_MODEL_FLEET_MODE")
        station_info_at = src.find('value_basis = "station.info"')
        assert fleet_at != -1 and station_info_at != -1
        # station.info assignment comes AFTER, so it overwrites the fleet mode.
        assert station_info_at > fleet_at

    def test_it_only_applies_when_nothing_better_exists(self):
        import inspect

        from tostools import audit_missing_attributes as m

        src = inspect.getsource(m._audit_entity)
        i = src.find("_MONUMENT_MODEL_FLEET_MODE")
        guard = src[max(0, i - 300) : i]
        assert "suggested_value is None" in guard
        assert 'entity_subtype == "monument"' in guard
        assert 'code == "model"' in guard


class TestProvenanceHonesty:
    """The string is the safeguard — it must not read as a finding."""

    @staticmethod
    def _basis():
        import inspect

        from tostools import audit_missing_attributes as m

        src = inspect.getsource(m._audit_entity)
        i = src.find("_MONUMENT_MODEL_FLEET_MODE")
        return src[i : i + 700]

    def test_it_says_it_is_a_mode(self):
        assert "fleet mode" in self._basis()

    def test_it_names_the_alternatives(self):
        b = self._basis()
        for other in ("steyptur stöpull", "pinni", "GPS stál-staur"):
            assert other in b, f"{other} not offered as an alternative"

    def test_it_demands_confirmation(self):
        assert "CONFIRM" in self._basis()

    def test_it_warns_that_this_is_published(self):
        # An operator must know this leaves the building before accepting it.
        b = self._basis()
        assert "site-log" in b or "site log" in b
