"""station_config data files must resolve from a WHEEL, not just a checkout.

`receivers epos-disseminate --station ISAK --sitelog` failed on rek-d01 with

    No such file or directory:
    '<venv>/lib/python3.13/data/station_config/antenna_arp.list'

because `get_data_file_path` computed `Path(__file__).parent…`, which is the
repo root for an editable install and `<venv>/lib/pythonX.Y` for a wheel. Site
logs had therefore never been generatable off a dev box — the same shape as the
attribute-catalog bug `data_files` was written to fix.
"""

from __future__ import annotations

from pathlib import Path

import tomllib

from tostools.legacy.gps_metadata_functions import get_data_file_path

REPO = Path(__file__).resolve().parent.parent
#: What the site-log renderer reads: §4 antenna reference point, §11 plate.
NEEDED = ("antenna_arp.list", "station-plate")


class TestResolution:
    def test_files_resolve_and_exist(self):
        for name in NEEDED:
            assert Path(get_data_file_path(name)).is_file(), name

    def test_resolver_is_not_cwd_dependent(self, tmp_path, monkeypatch):
        """The old fallback chain included a bare relative `data/` path."""
        monkeypatch.chdir(tmp_path)
        assert Path(get_data_file_path("antenna_arp.list")).is_file()

    def test_unknown_file_returns_a_path_not_a_crash(self):
        """Callers report the expected location when something is missing."""
        assert "no_such_file" in get_data_file_path("no_such_file")


class TestWheelPackaging:
    """The resolver alone is not enough — the wheel must carry the files."""

    def _force_include(self):
        with open(REPO / "pyproject.toml", "rb") as fh:
            cfg = tomllib.load(fh)
        return cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    def test_each_needed_file_is_shipped(self):
        shipped = self._force_include()
        for name in NEEDED:
            key = f"data/station_config/{name}"
            assert key in shipped, f"{name} would be missing from the wheel"
            assert shipped[key] == f"tostools/data/station_config/{name}"

    def test_the_whole_station_config_tree_is_not_shipped(self):
        """It is 56 MB — backups/, work/ and a 1.3 MB IERS list."""
        assert "data/station_config" not in self._force_include()

    def test_shipped_files_are_small(self):
        for name in NEEDED:
            size = (REPO / "data" / "station_config" / name).stat().st_size
            assert size < 100_000, f"{name} is {size} bytes — too big for a wheel"
