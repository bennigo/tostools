"""A suppressed antenna serial publishes as ``0000``, never as an empty field.

The synthetic ``<subtype>-<STID>-<YYYYMMDD>`` key must not be published — only
the first 5 characters reach SINEX, so ``antenna-eldc-20200129`` would be
distributed worldwide as ``anten``. The original fix blanked the field, on the
IGS instruction that an unknown optional answer is left empty.

**M3G refuses an empty antenna serial.** Established by bisecting VMEY's site
log against the live API on 2026-08-20, one variable at a time::

    M3G's own stored copy, verbatim         -> HTTP 200
    …with the antenna serial emptied        -> HTTP 422  'check the "Antenna" section'
    …with the radome changed NONE -> SCIS   -> HTTP 200
    our site log, blank serial              -> HTTP 422
    our site log, serial "0000"             -> HTTP 200

So the radome edit and the date corrections were never the problem; the empty
serial was, and only it. ``0000`` is non-empty for M3G, reads as ``0000`` in
SINEX rather than a misleading word fragment, and is already what both the RINEX
header convention and okada's GAMIT station.info carry for such an antenna.

Both generators are pinned. ``tosGPS sitelog`` renders through
``legacy.gps_metadata_functions``, NOT ``core.site_log``, so a fix applied to
only the modern module leaves the published artefact unchanged.
"""

from __future__ import annotations

import pathlib
from datetime import datetime

import pytest

from tostools.device import PUBLISHED_UNKNOWN_ANTENNA_SERIAL


def _session(serial):
    return [
        {
            "time_from": datetime(2023, 1, 11),
            "time_to": None,
            "antenna": {
                "model": "SEPCHOKE_B3E6",
                "serial_number": serial,
                "antenna_height": 0.0,
                "antenna_reference_point": "BPA",
            },
        }
    ]


def _serial_line(text):
    for ln in text.splitlines():
        if "Serial Number" in ln and "Radome" not in ln:
            return ln.split(":", 1)[1].strip()
    return None


class TestTheConstant:
    def test_it_is_0000(self):
        # Empirically the value M3G accepts; see the module docstring.
        assert PUBLISHED_UNKNOWN_ANTENNA_SERIAL == "0000"

    def test_it_is_not_empty(self):
        # The whole point: an empty antenna serial is a 422 from M3G.
        assert PUBLISHED_UNKNOWN_ANTENNA_SERIAL.strip() != ""


class TestTheLiveGeneratorIsFixed:
    def test_the_legacy_generator_imports_the_constant(self):
        # tosGPS sitelog publishes through THIS module. A fix applied only to
        # core/site_log.py would not change the published artefact at all.
        import tostools.legacy.gps_metadata_functions as legacy

        assert hasattr(legacy, "PUBLISHED_UNKNOWN_ANTENNA_SERIAL")


class TestLiveRendererIsTheLegacyOne:
    """Pin the wiring, not just the output.

    Both publishing paths render through
    ``legacy.gps_metadata_functions.site_log``;
    ``core.site_log.generate_igs_site_log`` has no production caller. Two
    docstrings claimed the reverse until 2026-08-22, which would send anyone
    fixing a published-output bug to a module that reaches nothing — the
    shape of the VMEY 422. If a future refactor swaps the wiring, that is a
    deliberate act and this test should be updated with it, not silently.
    """

    def test_both_callers_go_through_build_site_log(self):
        """One entry point, so the two cannot drift apart in ARGUMENTS.

        They previously called the renderer directly with different argument
        sets — receivers passed monument_number/country_code, tosGPS passed
        report_type/modified_sections — and agreed only because the omitted
        arguments shared defaults.
        """
        import inspect
        from pathlib import Path

        from tostools import tosGPS

        tosgps_src = inspect.getsource(tosGPS)
        assert "build_site_log(" in tosgps_src
        assert "gpsf.site_log(" not in tosgps_src, "tosGPS must not bypass it"

        sitelogs = (
            Path(__file__).resolve().parents[2]
            / "receivers/src/receivers/dissemination/sitelogs.py"
        )
        if not sitelogs.exists():
            pytest.skip("receivers package not available")
        rx_src = sitelogs.read_text(encoding="utf-8")
        assert "from tostools.core.site_log import build_site_log" in rx_src
        assert "import site_log as render_site_log" not in rx_src

    def test_build_site_log_renders_via_legacy(self):
        """build_site_log delegates to the legacy renderer, not the dead one."""
        import inspect

        from tostools.core.site_log import build_site_log

        src = inspect.getsource(build_site_log)
        assert "legacy.gps_metadata_functions import site_log" in src
        assert "generate_igs_site_log" not in src.split('"""')[-1]

    def test_report_type_follows_the_m3g_convention(self):
        """NEW for the first log in a dated series, UPDATE once one exists.

        receivers used to omit report_type entirely and inherit the renderer's
        unconditional 'UPDATE', so a first-ever log was mislabelled.
        """
        import inspect

        from tostools.core.site_log import build_site_log

        src = inspect.getsource(build_site_log)
        assert '"UPDATE" if previous_log else "NEW"' in src

    def test_core_renderer_has_no_production_caller(self):
        """Guard the claim in core/site_log.py's docstring."""
        from pathlib import Path

        src_root = Path(__file__).resolve().parents[1] / "src/tostools"
        callers = []
        for path in src_root.rglob("*.py"):
            if path.name == "site_log.py" and path.parent.name == "core":
                continue  # the definition itself
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "generate_igs_site_log" in line and not line.lstrip().startswith(
                    "#"
                ):
                    callers.append(f"{path.name}:{i}")
        assert not callers, (
            "core.site_log.generate_igs_site_log gained a caller: "
            f"{callers}. If that is intentional, the module docstring and "
            "receivers/dissemination/sitelogs.py must stop saying it is unused."
        )


class TestAutoFilenameTargetIsResolvedOnce:
    """The §0 search and the writer must use ONE resolved path.

    They were computed separately: the search looked in
    ``<dir>/<STATION_ID>/`` while ``--date-in-name`` wrote to
    ``<dir>/sitelog/<STATION_ID>/``. So the chain was built from a tree the
    writer never touched — every log looked first-in-series and a real
    series never chained.
    """

    class _Args:
        def __init__(self, dir_, date_in_name, custom_date=None):
            self.dir = dir_
            self.date_in_name = date_in_name
            self.custom_date = custom_date

    def test_date_in_name_nests_under_sitelog(self, tmp_path):
        from tostools.tosGPS import _resolve_sitelog_target

        full, name = _resolve_sitelog_target(
            self._Args(str(tmp_path), True, "20260823"), "RHOF"
        )
        assert name == "rhof00isl_20260823.log"
        assert str(tmp_path / "sitelog" / "RHOF00ISL") in full

    def test_a_dir_already_ending_in_sitelog_is_not_doubled(self, tmp_path):
        from tostools.tosGPS import _resolve_sitelog_target

        base = tmp_path / "sitelog"
        full, _ = _resolve_sitelog_target(
            self._Args(str(base), True, "20260823"), "RHOF"
        )
        assert "sitelog/sitelog" not in full

    def test_plain_auto_filename_is_flat(self, tmp_path):
        from tostools.tosGPS import _resolve_sitelog_target

        full, _ = _resolve_sitelog_target(
            self._Args(str(tmp_path), False, "20260823"), "RHOF"
        )
        assert "sitelog" not in str(pathlib.Path(full).parent.name)

    def test_the_search_dir_equals_the_write_dir(self, tmp_path):
        """The invariant the bug violated."""
        import inspect

        from tostools import tosGPS

        src = inspect.getsource(tosGPS)
        # The pre-render search must derive its directory from the resolved
        # target, never rebuild it from args.dir.
        assert "_target, _ = _resolve_sitelog_target(args, station)" in src
        assert "station_dir = os.path.join(args.dir, station_id)" not in src
