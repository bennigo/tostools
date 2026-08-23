"""F1 step 1: `device_structure` has one implementation on the tos_client path.

`gps_metadata_qc` exists twice — top-level and under `legacy/` — and the two
copies have diverged, with fixes landing on whichever side was in view. The
unification plan is `docs/architecture/legacy-fork-unification-plan.md`.

`device_structure` is the tractable half of the `api/tos_client.py` pair: the two
bodies are identical apart from how the module logger is constructed, so the
import moved to the surviving module.

Its sibling, `device_attribute_history`, could **not** be moved by analogy: the
legacy copy carried the GNSS constellation toggles (GAL/BDS/QZSS/SBAS/IRN) and
`azimuth`, the top-level one did not, and that call chain feeds the published
site log:

    core/site_log.py:127 -> get_complete_station_metadata
      -> get_device_sessions -> _get_device_attribute_history

Swapping it then would have silently dropped §3.3 Satellite System and §4
Alignment from every published log. F1 step 2 has since removed the hazard at
its source — both copies read `devices.SITELOG_GPS_ATTRIBUTE_CODES` — and the
import moved too. The guard for that half now lives in
`tests/test_f1_device_attribute_history_unified.py`, which asserts on rendered
site-log output rather than on import lines.
"""

from __future__ import annotations

import inspect
import logging

import pytest

SUBTYPES = (
    "gnss_receiver",
    "antenna",
    "radome",
    "monument",
    "modem",
    "sim",
    "router",
    "unknown_thing",
)

# The numeric fields device_structure runs through float(). "" is included on
# purpose: it raises, and the two copies must fail the same way, not merely
# succeed the same way.
NUMERIC_FIELDS = (
    "antenna_height",
    "monument_height",
    "antenna_offset_north",
    "antenna_offset_east",
    "azimuth",
)

_TEXT_FIELDS = (
    "model",
    "serial_number",
    "firmware_version",
    "software_version",
    "antenna_reference_point",
    "radome_serial_number",
    "date_from",
    "date_to",
    "name",
    "comment",
    "GPS",
    "GLO",
    "GAL",
    "BDS",
    "QZSS",
    "SBAS",
    "IRN",
    "sampling_interval",
)


def _device(subtype: str, numeric: str) -> dict:
    d = {f: f"v_{f}" for f in _TEXT_FIELDS}
    d["code_entity_subtype"] = subtype
    for k in NUMERIC_FIELDS:
        d[k] = numeric
    return d


def _call(fn, device):
    """Return the result, or a comparable marker for the raised exception."""
    try:
        return fn(device, logging.CRITICAL)
    except Exception as e:  # noqa: BLE001 - comparing failure modes is the point
        return ("EXC", type(e).__name__, str(e))


class TestTosClientUsesTheSurvivingCopy:
    def test_device_structure_is_imported_from_the_top_level_module(self):
        from tostools.api import tos_client

        src = inspect.getsource(tos_client.TOSClient._build_history_from_connections)
        assert "from ..gps_metadata_qc import device_structure" in src
        assert "from ..legacy.gps_metadata_qc import device_structure" not in src

    def test_no_legacy_device_structure_import_remains_anywhere(self):
        """Belt and braces: the method above is not the only place it could hide."""
        import pathlib

        import tostools.api.tos_client as tc

        src = pathlib.Path(tc.__file__).read_text()
        assert "from ..legacy.gps_metadata_qc import device_structure" not in src

    def test_the_attribute_history_import_has_also_moved_now(self):
        """Inverted deliberately when F1 step 2 landed.

        This assertion used to require the OPPOSITE — that the sibling import
        still pointed at `legacy` — because the two copies then carried
        different attribute key lists and repointing it would have dropped §3.3
        and §4 from every published site log.

        Step 2 removed the hazard at its source: both copies read
        `devices.SITELOG_GPS_ATTRIBUTE_CODES`, so the swap became
        behaviour-preserving and was made. The guard that replaces this one is
        `tests/test_f1_device_attribute_history_unified.py` — it renders a site
        log and asserts the constellations and azimuth survive, which is a
        stronger statement than which module the import names.
        """
        from tostools.api import tos_client

        src = inspect.getsource(tos_client.TOSClient._get_device_attribute_history)
        assert "from ..gps_metadata_qc import device_attribute_history" in src
        assert (
            "from ..legacy.gps_metadata_qc import device_attribute_history" not in src
        )


class TestTheTwoCopiesStillAgree:
    """Transitional guard — delete with `legacy/gps_metadata_qc.py` in F1 step 4.

    While both copies exist, an edit to one is a divergence. This makes that
    fail here instead of in production months later, which is exactly how the
    fork got this far.
    """

    @pytest.mark.parametrize("subtype", SUBTYPES)
    @pytest.mark.parametrize("numeric", ["0.1234", "0", "-1.5", ""])
    def test_identical_output_for(self, subtype, numeric):
        legacy_mod = pytest.importorskip("tostools.legacy.gps_metadata_qc")
        from tostools.gps_metadata_qc import device_structure as modern

        device = _device(subtype, numeric)
        assert _call(modern, dict(device)) == _call(
            legacy_mod.device_structure, dict(device)
        )
