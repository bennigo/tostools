"""Equipment-era resolution must not split on constellation boundaries.

`gps_metadata` -> `get_device_sessions` -> `device_attribute_history` is the
chain that decides WHICH EQUIPMENT ERA a given date belongs to. Its four
consumers all read equipment identity only — receiver/antenna/radome/DOMES —
and none reads a constellation or `azimuth` field:

    rinex/corrector.py:410   the archive header retrofit (`--fix-headers`)
    gps_rinex.py:992         RINEX QC / inconsistency report
    tosGPS.py:1414           `timespan` (TOS dates vs archive)
    tosGPS.py:2096           GAMIT `station.info`

A constellation boundary is **not** an era boundary, so the wide site-log
attribute set is actively wrong here. Two ways it hurts:

* `station.info` — a constellation split becomes a spurious duplicate
  occupation (docs/architecture/synthesis-legacy-divergence.md).
* `--fix-headers` — worse, and silent. `codes` gates
  `if item["code"] in key_list`, so widening lets more attribute rows move
  `date_from`/`date_to`. Via this kernel's Bug 1 a toggle starting mid-tenure
  can move a session's start ONTO the toggle date and drop the earlier window
  altogether. `corrector` then finds no session covering an older file and falls
  back to `device_history[-1]` — the most RECENT equipment — writing the wrong
  era into a historical RINEX header.

Regression history: F1 step 2 (`d467807`) collapsed the two attribute lists onto
one constant and made the WIDE set the default. That was right for the site-log
direction and wrong for this one; the commit message named only the deprecated
`--use-legacy-synthesis` chain, missing these four. The `codes=` pin at the call
site is the fix. No archive run happened in the window, so nothing was
mis-written.

The fixture uses the documented ISAK shape: a QZSS/SBAS boundary landing one day
off the firmware change.
"""

from __future__ import annotations

import logging

import pytest

from tostools.devices import LEGACY_GPS_ATTRIBUTE_CODES
from tostools.gps_metadata_qc import device_attribute_history

INSTALL = "2019-06-01T00:00:00"
FIRMWARE_BUMP = "2026-08-01T00:00:00"
CONSTELLATION_CHANGE = "2026-08-02T00:00:00"  # one day off — the ISAK sliver


def _attr(code, value, date_from, date_to=None):
    return {"code": code, "value": value, "date_from": date_from, "date_to": date_to}


def _receiver_with_misaligned_constellation():
    return {
        "id_entity": 4972,
        "code_entity_subtype": "gnss_receiver",
        "attributes": [
            _attr("serial_number", "3018434", INSTALL),
            _attr("model", "SEPT POLARX5", INSTALL),
            _attr("firmware_version", "5.6.0", INSTALL, FIRMWARE_BUMP),
            _attr("firmware_version", "5.7.0", FIRMWARE_BUMP),
            _attr("GPS", "true", INSTALL),
            _attr("GLO", "true", INSTALL),
            # Enabled years into the tenure, on its own boundary.
            _attr("QZSS", "true", CONSTELLATION_CHANGE),
        ],
    }


def _periods(rows):
    return [(r["date_from"], r["date_to"]) for r in rows]


def _covers(rows, when: str) -> bool:
    return any(
        r["date_from"] <= when and (r["date_to"] is None or when < r["date_to"])
        for r in rows
    )


class TestNarrowCodesKeepTheEquipmentEras:
    def test_the_install_era_still_exists(self):
        """The regression, stated as the thing that breaks a header retrofit.

        A file from 2020 must land in a session that covers 2020. If it does
        not, `corrector` silently uses the most recent equipment instead.
        """
        rows = device_attribute_history(
            _receiver_with_misaligned_constellation(),
            INSTALL,
            None,
            logging.CRITICAL,
            codes=LEGACY_GPS_ATTRIBUTE_CODES,
        )
        assert _covers(rows, "2020-07-01T00:00:00"), _periods(rows)

    def test_eras_split_on_firmware_but_not_on_the_constellation(self):
        rows = device_attribute_history(
            _receiver_with_misaligned_constellation(),
            INSTALL,
            None,
            logging.CRITICAL,
            codes=LEGACY_GPS_ATTRIBUTE_CODES,
        )
        starts = {d for d, _ in _periods(rows)}
        assert FIRMWARE_BUMP in starts, "a firmware change IS an era boundary"
        assert (
            CONSTELLATION_CHANGE not in starts
        ), "a constellation toggle is NOT an era boundary"

    @pytest.mark.parametrize(
        "field", ["serial_number", "model", "firmware_version", "antenna_height"]
    )
    def test_the_fields_the_consumers_actually_read_are_present(self, field):
        rows = device_attribute_history(
            _receiver_with_misaligned_constellation(),
            INSTALL,
            None,
            logging.CRITICAL,
            codes=LEGACY_GPS_ATTRIBUTE_CODES,
        )
        assert field in rows[0]


class TestTheCallSiteIsPinned:
    """The pin is a `codes=` argument, so nothing about the wide DEFAULT
    protects it — only this does. Mutation: drop the argument at
    `gps_metadata_qc.get_device_sessions` and this goes red."""

    def test_get_device_sessions_passes_the_narrow_list(self):
        import inspect

        from tostools.gps_metadata_qc import get_device_sessions

        src = inspect.getsource(get_device_sessions)
        assert "codes=LEGACY_GPS_ATTRIBUTE_CODES" in src, (
            "the era-resolution path must pin the narrow attribute list; "
            "the wide default splits sessions on constellation boundaries"
        )

    def test_the_wide_default_is_unchanged_for_everyone_else(self):
        """The pin must not have been implemented by reverting the default —
        the site-log direction still needs the wide set."""
        from tostools.devices import SITELOG_GPS_ATTRIBUTE_CODES

        rows = device_attribute_history(
            _receiver_with_misaligned_constellation(), INSTALL, None, logging.CRITICAL
        )
        for code in SITELOG_GPS_ATTRIBUTE_CODES:
            assert code in rows[0]
