"""Unit tests for :mod:`tostools.api.client_cache`.

No network: the inner client is a counting fake, so 'was this served from
disk' is observable as 'did the inner client get called again'.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tostools.api.client_cache import (
    DEFAULT_TTL_SECONDS,
    SNAPSHOT_VERSION,
    CachingClient,
    SnapshotClient,
    SnapshotMiss,
    cache_root,
    humanize_age,
)


class CountingClient:
    """Inner client that records how often each read was actually made."""

    def __init__(self, stations=None, entities=None):
        self._stations = stations if stations is not None else [{"id_entity": 1}]
        self._entities = entities or {}
        self.station_calls = 0
        self.entity_calls = 0

    def list_stations(self, domain="geophysical"):
        self.station_calls += 1
        return self._stations

    def get_entity_history(self, id_entity):
        self.entity_calls += 1
        return self._entities.get(int(id_entity), {"id_entity": int(id_entity)})

    def unrelated_method(self):
        return "passthrough"


@pytest.fixture
def cache_dir(tmp_path) -> Path:
    return tmp_path / "cache"


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


class TestCachingClient:
    def test_second_read_is_served_from_disk(self, cache_dir):
        inner = CountingClient()
        c1 = CachingClient(inner, cache_dir=cache_dir)
        c1.get_entity_history(42)
        assert inner.entity_calls == 1

        c2 = CachingClient(inner, cache_dir=cache_dir)
        c2.get_entity_history(42)
        assert inner.entity_calls == 1, "second run should not re-fetch"
        assert c2.hits == 1

    def test_station_listing_is_cached_too(self, cache_dir):
        inner = CountingClient()
        CachingClient(inner, cache_dir=cache_dir).list_stations()
        CachingClient(inner, cache_dir=cache_dir).list_stations()
        assert inner.station_calls == 1

    def test_expired_entry_refetches(self, cache_dir):
        inner = CountingClient()
        CachingClient(inner, cache_dir=cache_dir).get_entity_history(42)
        # ttl=0 → anything already on disk is stale
        CachingClient(inner, cache_dir=cache_dir, ttl=0).get_entity_history(42)
        assert inner.entity_calls == 2

    def test_refresh_ignores_disk_but_refills(self, cache_dir):
        inner = CountingClient()
        CachingClient(inner, cache_dir=cache_dir).get_entity_history(42)
        c = CachingClient(inner, cache_dir=cache_dir, refresh=True)
        c.get_entity_history(42)
        assert inner.entity_calls == 2
        assert c.hits == 0
        # refilled, so a subsequent normal run hits
        CachingClient(inner, cache_dir=cache_dir).get_entity_history(42)
        assert inner.entity_calls == 2

    def test_no_cache_neither_reads_nor_writes(self, cache_dir):
        inner = CountingClient()
        CachingClient(inner, cache_dir=cache_dir, enabled=False).get_entity_history(7)
        assert not (cache_dir / "entity-7.json").exists()
        CachingClient(inner, cache_dir=cache_dir, enabled=False).get_entity_history(7)
        assert inner.entity_calls == 2

    def test_null_history_is_not_cached(self, cache_dir):
        """A None answer may be transient; caching it would pin the gap."""

        class NoneClient(CountingClient):
            def get_entity_history(self, id_entity):
                self.entity_calls += 1
                return None

        inner = NoneClient()
        CachingClient(inner, cache_dir=cache_dir).get_entity_history(9)
        CachingClient(inner, cache_dir=cache_dir).get_entity_history(9)
        assert inner.entity_calls == 2

    def test_unknown_attribute_passes_through(self, cache_dir):
        c = CachingClient(CountingClient(), cache_dir=cache_dir)
        assert c.unrelated_method() == "passthrough"

    def test_corrupt_cache_file_falls_back_to_fetch(self, cache_dir):
        inner = CountingClient()
        CachingClient(inner, cache_dir=cache_dir).get_entity_history(42)
        (cache_dir / "entity-42.json").write_text("{not json", encoding="utf-8")
        CachingClient(inner, cache_dir=cache_dir).get_entity_history(42)
        assert inner.entity_calls == 2


class TestCacheNote:
    def test_none_when_nothing_hit(self, cache_dir):
        c = CachingClient(CountingClient(), cache_dir=cache_dir)
        c.get_entity_history(1)
        assert c.cache_note() is None

    def test_reports_hits_and_remedy(self, cache_dir):
        inner = CountingClient()
        CachingClient(inner, cache_dir=cache_dir).get_entity_history(1)
        c = CachingClient(inner, cache_dir=cache_dir)
        c.get_entity_history(1)
        note = c.cache_note()
        assert "1 hit" in note
        assert "--refresh" in note


class TestServerPartitioning:
    def test_different_servers_get_different_dirs(self):
        a = cache_root("vi-api.vedur.is:443")
        b = cache_root("test-tos.vedur.is:443")
        assert a != b

    def test_slug_is_filesystem_safe(self):
        p = cache_root("https://host/tos/internal")
        assert "/" not in p.name

    def test_no_server_returns_base(self):
        assert cache_root().name == "tos-read"


class TestHumanizeAge:
    @pytest.mark.parametrize(
        "seconds,expected",
        [(0, "0s"), (42, "42s"), (60, "1m"), (400, "6m"), (7200, "2h"), (200000, "2d")],
    )
    def test_formats(self, seconds, expected):
        assert humanize_age(seconds) == expected


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class TestSnapshot:
    def _record(self, cache_dir, tmp_path):
        inner = CountingClient(entities={5: {"id_entity": 5, "attributes": []}})
        c = CachingClient(inner, cache_dir=cache_dir)
        c.list_stations()
        c.get_entity_history(5)
        return c.write_snapshot(tmp_path / "snap.json", criteria=["x = y"]), inner

    def test_roundtrip_serves_without_network(self, cache_dir, tmp_path):
        path, inner = self._record(cache_dir, tmp_path)
        before = (inner.station_calls, inner.entity_calls)

        replay = SnapshotClient.load(path)
        assert replay.list_stations() == [{"id_entity": 1}]
        assert replay.get_entity_history(5)["id_entity"] == 5
        assert (inner.station_calls, inner.entity_calls) == before

    def test_records_creation_time_and_meta(self, cache_dir, tmp_path):
        path, _ = self._record(cache_dir, tmp_path)
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert payload["tostools_snapshot"] == SNAPSHOT_VERSION
        assert payload["created"].endswith("Z")
        assert payload["meta"]["criteria"] == ["x = y"]

    def test_note_states_no_live_read(self, cache_dir, tmp_path):
        path, _ = self._record(cache_dir, tmp_path)
        note = SnapshotClient.load(path).snapshot_note()
        assert "NO live TOS read" in note
        assert "recorded" in note

    def test_missing_entity_raises_not_empty(self, cache_dir, tmp_path):
        """The whole point: a gap must not read as 'no devices'."""
        path, _ = self._record(cache_dir, tmp_path)
        replay = SnapshotClient.load(path)
        with pytest.raises(SnapshotMiss, match="narrower query"):
            replay.get_entity_history(999)

    def test_missing_domain_raises(self, cache_dir, tmp_path):
        path, _ = self._record(cache_dir, tmp_path)
        with pytest.raises(SnapshotMiss, match="no station listing"):
            SnapshotClient.load(path).list_stations(domain="other")

    def test_records_even_with_cache_disabled(self, tmp_path):
        inner = CountingClient()
        c = CachingClient(inner, cache_dir=tmp_path / "c", enabled=False)
        c.list_stations()
        c.get_entity_history(3)
        payload = c.snapshot_payload()
        assert "3" in payload["entities"]

    def test_version_mismatch_is_rejected(self):
        with pytest.raises(ValueError, match="unsupported snapshot version"):
            SnapshotClient({"tostools_snapshot": 999})


class TestDefaults:
    def test_ttl_default_is_sane(self):
        assert 60 <= DEFAULT_TTL_SECONDS <= 3600
