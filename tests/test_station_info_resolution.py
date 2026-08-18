"""station.info is resolved like every other authority, not hardcoded.

The remediation runbook used to spell out
``--station-info data/station_config/station.info.sopac.apr05`` — a packaged
2005 snapshot named by hand, in a pipeline whose stated premise is "no
hardcoded paths, no one-off scripts". Worse, without that flag the audits did
no station.info enrichment at all, so the hardcoded path was load-bearing.
"""

import pytest

from tostools.standards.gamit_station_info import (
    CANONICAL_REMOTE,
    StationInfoSource,
    resolve_station_info,
)


class TestPrecedence:
    def test_explicit_override_wins(self, tmp_path):
        f = tmp_path / "mine.info"
        f.write_text("x")
        assert resolve_station_info(f).origin == "override"

    def test_env_beats_config_and_packaged(self, tmp_path, monkeypatch):
        f = tmp_path / "env.info"
        f.write_text("x")
        monkeypatch.setenv("TOSTOOLS_STATION_INFO", str(f))
        src = resolve_station_info()
        assert src.origin == "env"
        assert src.path == f

    def test_override_beats_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOSTOOLS_STATION_INFO", str(tmp_path / "env.info"))
        src = resolve_station_info(tmp_path / "flag.info")
        assert src.origin == "override"

    def test_falls_back_to_something(self, monkeypatch):
        # With no override and no env, resolution must still yield a file —
        # a station.info is always better than none for these audits, so this
        # never raises the way the archive-root resolver does.
        monkeypatch.delenv("TOSTOOLS_STATION_INFO", raising=False)
        assert resolve_station_info() is not None


class TestOriginReporting:
    """The point of the resolver: 'which copy did I read, and is it live?'"""

    def test_packaged_is_flagged_as_a_snapshot(self, tmp_path):
        s = StationInfoSource(tmp_path / "x", "packaged")
        assert s.is_snapshot is True
        assert "SNAPSHOT" in s.describe()
        assert CANONICAL_REMOTE in s.describe()

    @pytest.mark.parametrize("origin", ["override", "env", "config", "mount"])
    def test_live_sources_are_not_snapshots(self, tmp_path, origin):
        s = StationInfoSource(tmp_path / "x", origin)
        assert s.is_snapshot is False
        assert "SNAPSHOT" not in s.describe()

    def test_describe_survives_a_missing_file(self, tmp_path):
        # Reporting must never be the thing that raises.
        s = StationInfoSource(tmp_path / "gone.info", "mount")
        assert "gone.info" in s.describe()

    def test_canonical_remote_names_host_and_path(self):
        assert "okada" in CANONICAL_REMOTE
        assert "/D/DATABASE/GAMIT/" in CANONICAL_REMOTE
