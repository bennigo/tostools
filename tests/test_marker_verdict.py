"""Marker mismatches get a deterministic verdict: typo / foreign / unconfirmed.

`compare_rinex_to_tos` now classifies a MARKER NAME / MARKER NUMBER mismatch so
a caller can act without a human in the loop. The decision is:

* ``typo``        — the receiver serial (hardware identity) or the coordinates
                    tie the file to THIS station, so the marker header is wrong
                    and rewriting it is safe.
* ``foreign``     — the file sits beyond the correction bound: another site's
                    data, never rewrite anything (pre-existing gate).
* ``unconfirmed`` — neither signal; the marker write is dropped (the discrepancy
                    is kept so a blocking gate still fires).

The BJTV-class bug this encodes: a file whose MARKER NAME is a foreign 4-char id
(e.g. ``GJFV``) but whose receiver serial matches the station is a header typo,
not another site's data — the SN is hardware identity, so it decides the case
that a rough APPROX POSITION (tens of metres off, as a receiver's own autonomous
fix legitimately is) cannot.
"""

from __future__ import annotations

from tostools.rinex.validator import compare_rinex_to_tos

XYZ = (2602395.8525, -1079316.1949, 5703116.2468)
LLH = (63.86315442, -22.52571320, 117.0119)
ALASKA_XYZ = (-2339489.8656, -2321414.2222, 5442334.8089)


def _rinex_info(xyz, marker="GJFV", rec_serial="3025064"):
    rec_line = f"{rec_serial:<20}{'POLARX5':<20}{'5.6.0':<20}"
    return {
        "file_name": "ELDC0420.22D.Z",
        "MARKER NAME": marker,
        "MARKER NUMBER": "",
        "REC # / TYPE / VERS": rec_line,
        "OBSERVER / AGENCY": f"{'GNSSatIMO':<20}{'Icelandic Meteorological Office':<40}",
        "APPROX POSITION XYZ": "{:.4f} {:.4f} {:.4f}".format(*xyz),
    }


def _tos_session(rec_serial="3025064"):
    return {
        "marker": "ELDC",
        "domes": "10202M001",
        "observer": "GNSSatIMO",
        "agency": "Icelandic Meteorological Office",
        "lat": LLH[0],
        "lon": LLH[1],
        "altitude": LLH[2],
        "gnss_receiver": {
            "serial_number": rec_serial,
            "model": "POLARX5",
            "firmware_version": "5.6.0",
        },
    }


class TestMarkerTypoWhenReceiverConfirms:
    def test_matching_serial_makes_a_marker_mismatch_a_typo(self):
        result = compare_rinex_to_tos(_rinex_info(XYZ), _tos_session())
        assert result["marker_verdict"]["verdict"] == "typo"
        # The marker rewrite is safe to keep.
        assert "MARKER NAME" in result["corrections"]

    def test_coordinates_make_a_marker_mismatch_a_typo_even_if_serial_differs(self):
        # Different serial (hardware swap) but the position is this station's.
        result = compare_rinex_to_tos(_rinex_info(XYZ), _tos_session("9999999"))
        assert result["marker_verdict"]["verdict"] == "typo"
        assert "MARKER NAME" in result["corrections"]


class TestMarkerUnconfirmedWhenNothingConfirms:
    def test_rough_position_with_foreign_serial_is_unconfirmed(self):
        # ~50 m off (within the correction bound, beyond coord_tolerance) and a
        # serial that does not match: neither signal ties it to this station.
        near = (XYZ[0] + 30.0, XYZ[1] + 30.0, XYZ[2] + 30.0)
        result = compare_rinex_to_tos(_rinex_info(near), _tos_session("9999999"))
        assert result["marker_verdict"]["verdict"] == "unconfirmed"
        # The marker write must NOT go out blind.
        assert "MARKER NAME" not in result["corrections"]
        # But the discrepancy is kept so a blocking gate still fires.
        assert "marker" in result["discrepancies"]


class TestMarkerForeignWhenAnotherSite:
    def test_a_foreign_file_is_foreign_not_unconfirmed(self):
        result = compare_rinex_to_tos(_rinex_info(ALASKA_XYZ), _tos_session())
        assert result["marker_verdict"]["verdict"] == "foreign"
        assert result["corrections"] == {}
