"""Triage files must land in gps-tos-corrections, not the current directory.

`resolve_triage_path` exists to remove exactly that footgun, but the
constellations verb wrote its `--triage-path` argument raw — so
`--triage-path isak.txt` silently produced a file wherever the operator was
standing, outside the repo that is supposed to hold the fleet's correction
history.
"""

from __future__ import annotations

from pathlib import Path

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
    """The repo convention is <repo>/<sta>/<sta>_<topic>_<YYYYMMDD>.txt.

    107 files follow it (e.g. nyla/nyla_constellations_20260710.txt) against 8
    under the data/triage/<stn>/ layout `default_triage_path` builds — so the
    auto-written file must use the station dir directly, reusing only the
    date-stamped filename. This mirrors what fleet_ops already does.
    """

    def _auto_path(self, station: str, root: Path) -> Path:
        from tostools.station_triage import default_triage_path

        canonical = default_triage_path(station)
        return (
            root
            / station.lower()
            / canonical.name.replace("_audit_", "_constellations_")
        )

    def test_station_dir_sits_directly_under_the_repo(self, tmp_path):
        p = self._auto_path("ISAK", tmp_path)
        assert p.parent == tmp_path / "isak", "must not nest under data/triage/"
        assert "data" not in p.relative_to(tmp_path).parts

    def test_filename_matches_the_established_pattern(self, tmp_path):
        """Same shape as the existing nyla/nyla_constellations_YYYYMMDD.txt."""
        import re

        p = self._auto_path("ISAK", tmp_path)
        assert re.fullmatch(r"isak_constellations_\d{8}\.txt", p.name), p.name

    def test_does_not_collide_with_the_generic_station_audit(self, tmp_path):
        from tostools.station_triage import default_triage_path

        audit = default_triage_path("ISAK", base_dir=tmp_path)
        assert self._auto_path("ISAK", tmp_path).name != audit.name


class TestParentCreation:
    def test_nested_parents_are_created(self, tmp_path, monkeypatch):
        """The per-station subdirectory will not exist on a first sweep."""
        monkeypatch.setenv("TOS_TRIAGE_DIR", str(tmp_path))
        target = resolve_triage_path("data/triage/isak/isak_constellations.txt")
        assert not target.parent.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# ACTION ...\n")
        assert target.read_text().startswith("# ACTION")


class TestSelfDocumentingApplyCommand:
    """The file must carry the command that applies it.

    Reconstructing `tos audit apply <path>` by hand after uncommenting is the
    step that gets fumbled — a `<file>` placeholder does not help, so the
    resolved path is baked in.
    """

    def _report(self):
        from datetime import date

        from tostools.audit_constellations import (
            ReceiverPeriodConstellations,
            StationConstellationHistoryReport,
        )

        return StationConstellationHistoryReport(
            station_id=4346,
            station_name="Ísakot",
            marker="ISAK",
            periods=[
                ReceiverPeriodConstellations(
                    device_id=4972,
                    serial="3018434",
                    model="SEPT POLARX5",
                    date_from=date(2017, 7, 4),
                    date_to=None,
                    reliable=True,
                    missing=[("QZSS", date(2025, 1, 27))],
                )
            ],
        )

    def test_header_carries_the_literal_apply_command(self, tmp_path):
        from tostools.audit_constellations import format_history_triage

        target = tmp_path / "isak" / "isak_constellations_20260802.txt"
        out = "\n".join(format_history_triage(self._report(), apply_path=target))
        assert f"tos audit apply {target}" in out

    def test_shows_both_dry_run_and_commit_forms(self, tmp_path):
        from tostools.audit_constellations import format_history_triage

        target = tmp_path / "isak.txt"
        out = "\n".join(format_history_triage(self._report(), apply_path=target))
        assert f"tos audit apply {target} --apply" in out
        assert "dry-run" in out

    def test_no_placeholder_token_survives(self, tmp_path):
        """A <file> placeholder would defeat copy-paste."""
        from tostools.audit_constellations import format_history_triage

        out = "\n".join(
            format_history_triage(self._report(), apply_path=tmp_path / "x.txt")
        )
        assert "<file>" not in out and "<this_file>" not in out

    def test_omitted_when_no_path_is_known(self):
        """Stdout rendering has no destination, so it must not invent one."""
        from tostools.audit_constellations import format_history_triage

        out = "\n".join(format_history_triage(self._report()))
        assert "tos audit apply" not in out

    def test_the_apply_line_is_commented(self, tmp_path):
        """It must not be parsed as an ACTION when the file is applied."""
        from tostools.audit_constellations import format_history_triage

        target = tmp_path / "isak.txt"
        for line in format_history_triage(self._report(), apply_path=target):
            if "tos audit apply" in line:
                assert line.lstrip().startswith("#"), line
