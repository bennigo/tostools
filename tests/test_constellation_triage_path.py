"""Triage files must land in gps-tos-corrections, not the current directory.

`resolve_triage_path` exists to remove exactly that footgun, but the
constellations verb wrote its `--triage-path` argument raw — so
`--triage-path isak.txt` silently produced a file wherever the operator was
standing, outside the repo that is supposed to hold the fleet's correction
history.
"""

from __future__ import annotations

from tostools.archive import resolve_triage_path, tos_corrections_dir


class TestResolution:
    def test_bare_name_goes_to_the_corrections_repo(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOS_TRIAGE_DIR", str(tmp_path))
        assert resolve_triage_path("isak.txt") == tmp_path / "isak.txt"

    def test_nested_relative_name_too(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOS_TRIAGE_DIR", str(tmp_path))
        got = resolve_triage_path("data/triage/isak/isak_constellations.txt")
        assert got == tmp_path / "data/triage/isak/isak_constellations.txt"

    def test_absolute_path_is_respected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOS_TRIAGE_DIR", str(tmp_path))
        explicit = tmp_path / "elsewhere" / "x.txt"
        assert resolve_triage_path(explicit) == explicit

    def test_env_var_overrides_the_default_repo(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOS_TRIAGE_DIR", str(tmp_path / "custom"))
        assert tos_corrections_dir() == tmp_path / "custom"

    def test_existing_relative_path_keeps_legacy_behaviour(self, tmp_path, monkeypatch):
        """A relative path that already exists stays cwd-relative — the
        resolver is explicitly backward-compatible on that case."""
        monkeypatch.setenv("TOS_TRIAGE_DIR", str(tmp_path / "corrections"))
        monkeypatch.chdir(tmp_path)
        here = tmp_path / "already.txt"
        here.write_text("x")
        assert resolve_triage_path("already.txt") == here.resolve()


class TestDefaultName:
    def test_lands_under_the_corrections_repo(self, tmp_path, monkeypatch):
        from tostools.station_triage import default_triage_path

        monkeypatch.setenv("TOS_TRIAGE_DIR", str(tmp_path))
        p = default_triage_path("ISAK", base_dir=tos_corrections_dir())
        assert tmp_path in p.parents
        assert "isak" in str(p)

    def test_constellation_variant_is_distinguishable(self, tmp_path):
        """Constellation sweeps must not overwrite the generic station audit
        file for the same station on the same day."""
        from tostools.station_triage import default_triage_path

        base = default_triage_path("ISAK", base_dir=tmp_path)
        con = base.with_name(base.name.replace("_audit_", "_constellations_"))
        assert con != base
        assert con.parent == base.parent
        assert "_constellations_" in con.name


class TestParentCreation:
    def test_nested_parents_are_created(self, tmp_path, monkeypatch):
        """The per-station subdirectory will not exist on a first sweep."""
        monkeypatch.setenv("TOS_TRIAGE_DIR", str(tmp_path))
        target = resolve_triage_path("data/triage/isak/isak_constellations.txt")
        assert not target.parent.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# ACTION ...\n")
        assert target.read_text().startswith("# ACTION")
