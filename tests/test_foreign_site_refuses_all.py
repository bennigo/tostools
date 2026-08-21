"""A file from another site gets NO header corrections at all.

`compare_rinex_to_tos` refuses to rewrite APPROX POSITION when the header sits
more than `_MAX_POSITION_CORRECTION_M` from TOS. That refusal used to gate only
the position, while the marker / DOMES / observer blocks that run afterwards
kept proposing writes — so `--fix-headers` edited files it had just identified
as belonging to another site.

Measured 2026-08-20:

* ELDC's six Alaska/UNAVCO strays had OBSERVER/AGENCY rewritten from
  "Jeffrey Freymueller University of Alaska-Fairbanks" to IMO's, and their
  MARKER NUMBER stripped.
* NYLA3420.14D.Z — recorded 6,361 km from NYLA — was stamped with NYLA's own
  IERS DOMES, 10230M001. That is an identity claim on foreign data.

"Correct these headers against this station's TOS record" is not a meaningful
operation on a file that is not this station's. The only valid outcomes are move
it or remove it, and editing it destroys the evidence needed to choose.
"""

from __future__ import annotations

from tostools.rinex.validator import compare_rinex_to_tos

# ELDC's surveyed ECEF (63.863 N, -22.526 E, 117 m — Iceland) and the position
# its strays actually carry: 58.972 N, -135.222 E, 13 m — SOUTHEAST ALASKA,
# which is why the observer reads University of Alaska-Fairbanks. ("ALERTGEO
# RESOLUTE" in REC # / TYPE is the receiver MODEL, not a place — do not read
# it as Resolute, Nunavut.)
ELDC_XYZ = (2602395.8525, -1079316.1949, 5703116.2468)
ELDC_LLH = (63.86315442, -22.52571320, 117.0119)
ALASKA_XYZ = (-2339489.8656, -2321414.2222, 5442334.8089)


def _rinex_info(xyz, observer="Jeffrey Freymueller University of Alaska-Fairbanks"):
    return {
        "file_name": "ELDC0420.22D.Z",
        "MARKER NAME": "ELDC",
        "MARKER NUMBER": "",
        "OBSERVER / AGENCY": f"{observer:<20}",
        "APPROX POSITION XYZ": "{:.4f} {:.4f} {:.4f}".format(*xyz),
    }


def _tos_session():
    return {
        "marker": "ELDC",
        "domes": "10202M001",
        "observer": "GNSSatIMO",
        "agency": "Icelandic Meteorological Office",
        "lat": ELDC_LLH[0],
        "lon": ELDC_LLH[1],
        "altitude": ELDC_LLH[2],
    }


class TestForeignSiteRefusesEverything:
    def test_an_alaska_file_gets_no_corrections_at_all(self):
        result = compare_rinex_to_tos(_rinex_info(ALASKA_XYZ), _tos_session())
        assert result["corrections"] == {}, (
            "a file from another site must receive NO header writes — "
            f"got {sorted(result['corrections'])}"
        )

    def test_it_is_flagged_as_foreign_with_an_action(self):
        result = compare_rinex_to_tos(_rinex_info(ALASKA_XYZ), _tos_session())
        foreign = result.get("foreign_site")
        assert foreign, "the refusal must be visible to callers, not just logged"
        assert foreign["distance_m"] > foreign["bound_m"]
        assert "archive-sort" in foreign["action"] or "remove" in foreign["action"]

    def test_discrepancies_are_kept_so_a_blocking_gate_still_fires(self):
        # Refusing to WRITE is not the same as declaring the file clean.
        result = compare_rinex_to_tos(_rinex_info(ALASKA_XYZ), _tos_session())
        assert result["discrepancies"], "a foreign file must not look clean"

    def test_the_observer_rewrite_that_erased_provenance_is_gone(self):
        result = compare_rinex_to_tos(_rinex_info(ALASKA_XYZ), _tos_session())
        assert "OBSERVER / AGENCY" not in result["corrections"]

    def test_the_domes_stamp_on_foreign_data_is_gone(self):
        # The NYLA case: stamping our IERS number onto another site's file.
        result = compare_rinex_to_tos(_rinex_info(ALASKA_XYZ), _tos_session())
        assert "MARKER NUMBER" not in result["corrections"]

    def test_what_was_dropped_is_recorded(self):
        result = compare_rinex_to_tos(_rinex_info(ALASKA_XYZ), _tos_session())
        assert "dropped_corrections" in result["foreign_site"]


class TestNormalFilesAreUnaffected:
    def test_a_local_file_still_gets_its_corrections(self):
        # The guard must not suppress ordinary repairs — that would silently
        # turn --fix-headers into a no-op fleet-wide.
        result = compare_rinex_to_tos(_rinex_info(ELDC_XYZ), _tos_session())
        assert result.get("foreign_site") is None
        assert "OBSERVER / AGENCY" in result["corrections"]

    def test_a_metre_scale_offset_is_still_correctable(self):
        near = (ELDC_XYZ[0] + 5.0, ELDC_XYZ[1] + 5.0, ELDC_XYZ[2] + 5.0)
        result = compare_rinex_to_tos(_rinex_info(near), _tos_session())
        assert result.get("foreign_site") is None
