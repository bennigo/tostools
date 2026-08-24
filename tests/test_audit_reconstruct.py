"""Reconciliation engine for `tos audit reconstruct-from-archive`.

The fixture is KOSK's KNOWN-CORRECT answer key, established this session from
three independent authorities that all agree (rinex-timeline, station.info,
verify-from-rinex):

  receiver:  SEPT POLARX2 sn=3160        2006-11-08 → 2019-09-24
             TRIMBLE NETR9 sn=5548R50633 2019-09-25 → now
  antenna:   AERAT2775_42 sn=5923        2006-11-08 → 2019-09-24  (composite h=1.0440)
             TRM57971.00 sn=1441137916   2019-09-25 → now         (composite h=1.0070)

TOS wrongly has BOTH current-era devices joined from 2006-06-29, and the whole
first era missing. The engine must: (1) emit patch-join-date for both open joins
→ 2019-09-25, (2) flag both first-era devices as MISSING, (3) raise the
composite-split review note.
"""

from __future__ import annotations

from tostools.audit_reconstruct import (
    ANTENNA,
    BUCKET_ATTACHED,
    BUCKET_CREATE,
    BUCKET_REOPEN,
    RECEIVER,
    ArchiveEra,
    SerialHit,
    StationInfoEra,
    TosJoin,
    format_triage,
    reconcile_eras,
)

# --- KOSK answer key -------------------------------------------------------

KOSK_ARCHIVE = [
    ArchiveEra(RECEIVER, "SEPT POLARX2", "3160", "2006-11-08", "2019-09-24"),
    ArchiveEra(RECEIVER, "TRIMBLE NETR9", "5548R50633", "2019-09-25", "2026-08-09"),
    ArchiveEra(ANTENNA, "AERAT2775_42", "5923", "2006-11-08", "2019-09-24"),
    ArchiveEra(ANTENNA, "TRM57971.00", "1441137916", "2019-09-25", "2026-08-09"),
]

# TOS: both current devices backdated to 2006-06-29, first era absent.
KOSK_TOS = [
    TosJoin(4835, 5937, RECEIVER, "5548R50633", "2006-06-29", None),
    TosJoin(4571, 5931, ANTENNA, "1441137916", "2006-06-29", None),
]

KOSK_INSTALL = {RECEIVER: "2019-09-25", ANTENNA: "2019-09-25"}


def _report():
    return reconcile_eras("KOSK", KOSK_ARCHIVE, KOSK_TOS, current_install=KOSK_INSTALL)


class TestKoskAnswerKey:
    def test_both_open_joins_get_backdated_fix(self):
        r = _report()
        fixed = {(f.child_id, f.subtype): f for f in r.join_fixes}
        assert (4835, RECEIVER) in fixed
        assert (4571, ANTENNA) in fixed
        for f in r.join_fixes:
            assert f.tos_time_from == "2006-06-29"
            assert f.archive_install == "2019-09-25"

    def test_patch_join_date_line_format(self):
        r = _report()
        rec = next(f for f in r.join_fixes if f.child_id == 4835)
        # Must match the verb the apply engine dispatches (verify-from-rinex shape).
        assert rec.action_line().startswith(
            "ACTION 4835 patch-join-date 5937 time_from 2019-09-25"
        )
        assert "# was 2006-06-29" in rec.action_line()

    def test_first_era_devices_flagged_missing(self):
        r = _report()
        missing = {(m.subtype, m.serial) for m in r.missing_eras}
        assert (RECEIVER, "3160") in missing  # POLARX2
        assert (ANTENNA, "5923") in missing  # AERAT2775_42
        # The current-era serials are present in TOS → never "missing".
        assert (RECEIVER, "5548R50633") not in missing
        assert (ANTENNA, "1441137916") not in missing

    def test_composite_split_review_raised(self):
        r = _report()
        assert any("COMPOSITE" in note for note in r.review)

    def test_triage_emits_uncommented_fixes_and_commented_review(self):
        r = _report()
        text = format_triage(r, apply_path="kosk/kosk_reconstruct.txt")
        # Deterministic fixes uncommented:
        assert "\nACTION 4835 patch-join-date 5937 time_from 2019-09-25" in text
        assert "\nACTION 4571 patch-join-date 5931 time_from 2019-09-25" in text
        # Missing eras only in the commented REVIEW block:
        assert "# REVIEW" in text
        assert "MISSING gnss_receiver: SEPT POLARX2 sn=3160" in text
        assert "MISSING antenna: AERAT2775_42 sn=5923" in text


class TestReconcileEdgeCases:
    def test_clean_when_tos_matches_archive(self):
        """Open join already at the archive install date → no fix, no missing."""
        archive = [
            ArchiveEra(
                RECEIVER, "TRIMBLE NETR9", "5548R50633", "2019-09-25", "2026-08-09"
            ),
        ]
        tos = [TosJoin(4835, 5937, RECEIVER, "5548R50633", "2019-09-25", None)]
        r = reconcile_eras(
            "TEST", archive, tos, current_install={RECEIVER: "2019-09-25"}
        )
        assert r.is_clean

    def test_no_fix_when_join_starts_after_install(self):
        """A join at/after the install date is never 'backdated'."""
        tos = [TosJoin(1, 2, RECEIVER, "S", "2020-01-01", None)]
        r = reconcile_eras("T", [], tos, current_install={RECEIVER: "2019-09-25"})
        assert r.join_fixes == []

    def test_closed_joins_are_not_backdate_fixed(self):
        """Only OPEN joins are candidates for the current-unit backdate fix."""
        tos = [TosJoin(1, 2, RECEIVER, "S", "2006-01-01", "2019-09-24")]
        r = reconcile_eras("T", [], tos, current_install={RECEIVER: "2019-09-25"})
        assert r.join_fixes == []

    def test_serial_match_is_case_and_space_insensitive(self):
        archive = [
            ArchiveEra(RECEIVER, "M", " 5548r50633 ", "2019-09-25", "2026-08-09")
        ]
        tos = [TosJoin(1, 2, RECEIVER, "5548R50633", "2019-09-25", None)]
        r = reconcile_eras("T", archive, tos, current_install={RECEIVER: "2019-09-25"})
        assert r.missing_eras == []

    def test_missing_install_date_skips_subtype(self):
        """No archive install date (empty archive for that subtype) → no fix."""
        tos = [TosJoin(1, 2, RECEIVER, "S", "2006-01-01", None)]
        r = reconcile_eras("T", [], tos, current_install={RECEIVER: None})
        assert r.join_fixes == []

    def test_joinfix_subtypes_can_exclude_receiver(self):
        """When the receiver fix is sourced elsewhere, the engine can skip it —
        but still detects the missing receiver era."""
        r = reconcile_eras(
            "KOSK",
            KOSK_ARCHIVE,
            KOSK_TOS,
            current_install=KOSK_INSTALL,
            joinfix_subtypes=(ANTENNA,),
        )
        assert all(f.subtype == ANTENNA for f in r.join_fixes)
        assert any(m.subtype == RECEIVER for m in r.missing_eras)


def _lookup(mapping):
    return lambda serial, subtype: mapping.get(serial.strip())


class TestSerialDupGuard:
    """Missing eras are classified adopt-vs-create by the injected dup-guard."""

    def test_reopen_bucket_becomes_create_join_adopt(self):
        hit = SerialHit(BUCKET_REOPEN, entity_id=9001, parent="B9", summary="detached")
        r = reconcile_eras(
            "KOSK",
            KOSK_ARCHIVE,
            KOSK_TOS,
            current_install=KOSK_INSTALL,
            station_id=4356,
            serial_lookup=_lookup({"3160": hit, "5923": hit}),
        )
        polarx = next(m for m in r.missing_eras if m.serial == "3160")
        assert polarx.is_adopt and polarx.adopt_entity_id == 9001
        text = format_triage(r)
        assert "ACTION 9001 create-join 4356 2006-11-08 2019-09-24" in text
        assert "adopt existing detached devices" in text

    def test_create_bucket_emits_copy_paste_template(self):
        hit = SerialHit(
            BUCKET_CREATE, entity_id=None, parent=None, summary="provably absent"
        )
        r = reconcile_eras(
            "KOSK",
            KOSK_ARCHIVE,
            KOSK_TOS,
            current_install=KOSK_INSTALL,
            station_id=4356,
            serial_lookup=_lookup({"3160": hit, "5923": hit}),
        )
        assert not any(m.is_adopt for m in r.missing_eras)
        text = format_triage(r)
        # A ready receivers-cfg intake line + the follow-up create-join, pre-filled:
        assert "receivers cfg add-receiver" in text and "--serial 3160" in text
        assert "receivers cfg add-antenna" in text and "--serial 5923" in text
        assert "#ACTION <new_id> create-join 4356 2006-11-08 2019-09-24" in text

    def test_attached_bucket_surfaces_dupguard_warning(self):
        hit = SerialHit(
            BUCKET_ATTACHED,
            entity_id=42,
            parent="OTHR",
            summary="Exists as id_entity=42, attached to OTHR.",
        )
        r = reconcile_eras(
            "KOSK",
            KOSK_ARCHIVE,
            KOSK_TOS,
            current_install=KOSK_INSTALL,
            station_id=4356,
            serial_lookup=_lookup({"3160": hit, "5923": hit}),
        )
        text = format_triage(r)
        assert "attached elsewhere" in text
        assert "attached to OTHR" in text

    def test_no_lookup_reports_unclassified(self):
        r = reconcile_eras(
            "KOSK",
            KOSK_ARCHIVE,
            KOSK_TOS,
            current_install=KOSK_INSTALL,
            station_id=4356,
            serial_lookup=None,
        )
        text = format_triage(r)
        assert "serial dup-guard not run" in text


class TestStationInfoEnrichment:
    def test_missing_era_carries_curated_model_and_composite_height(self):
        si = [
            StationInfoEra(
                ANTENNA,
                "AERAT2775_42",
                "5923",
                "2006-06-29",
                "2019-09-24",
                composite_height="1.0440",
            ),
            StationInfoEra(
                RECEIVER, "SEPT POLARX2", "3160", "2006-06-29", "2019-09-24"
            ),
        ]
        r = reconcile_eras(
            "KOSK",
            KOSK_ARCHIVE,
            KOSK_TOS,
            current_install=KOSK_INSTALL,
            station_id=4356,
            station_info=si,
        )
        ant = next(m for m in r.missing_eras if m.serial == "5923")
        assert ant.canonical_model == "AERAT2775_42"
        assert ant.composite_height == "1.0440"
        text = format_triage(r, station_info_path="station.info.sopac")
        assert "station.info h=1.0440" in text

    def test_companion_audit_footer_names_the_station(self):
        r = _report()
        text = format_triage(r, station_info_path="data/station.info.sopac")
        assert "tos audit missing-attributes KOSK --history" in text
        assert "tos audit attribute-dates KOSK" in text
        assert "tos audit firmware-chain KOSK" in text
        assert "kosk/kosk_attrs.txt" in text


class TestStationInfoDatePreference:
    """station.info's curated install/removal dates beat the archive's
    first/last-data days (the KOSK one-day + end-gap correction)."""

    def test_joinfix_prefers_station_info_install_date(self):
        # archive says the NETR9 install is 2019-09-25; station.info says 09-24.
        si = [
            StationInfoEra(RECEIVER, "TRIMBLE NETR9", "5548R50633", "2019-09-24", None),
            StationInfoEra(ANTENNA, "TRM57971.00", "1441137916", "2019-09-24", None),
        ]
        r = reconcile_eras(
            "KOSK",
            KOSK_ARCHIVE,
            KOSK_TOS,
            current_install={RECEIVER: "2019-09-25", ANTENNA: "2019-09-25"},
            station_id=4356,
            station_info=si,
        )
        for f in r.join_fixes:
            assert f.archive_install == "2019-09-24"  # station.info, not archive
        # divergence is surfaced
        assert any("using station.info 2019-09-24" in n for n in r.review)

    def test_missing_era_uses_station_info_dates_and_notes_archive(self):
        # archive antenna era ended 2019-07-02 (data gap before the swap);
        # station.info carries the true removal 2019-09-24 and install 2006-06-29.
        archive = [
            ArchiveEra(ANTENNA, "AERO2775-54", "5923", "2006-11-08", "2019-07-02"),
        ]
        tos = [TosJoin(4571, 5525, ANTENNA, "1441137916", "2019-09-24", None)]
        si = [
            StationInfoEra(
                ANTENNA,
                "AERAT2775_42",
                "5923",
                "2006-06-29",
                "2019-09-24",
                composite_height="1.0440",
            ),
        ]
        r = reconcile_eras(
            "KOSK",
            archive,
            tos,
            current_install={ANTENNA: "2019-09-24"},
            station_id=4356,
            station_info=si,
        )
        ant = next(m for m in r.missing_eras if m.serial == "5923")
        assert ant.date_from == "2006-06-29" and ant.date_to == "2019-09-24"
        assert ant.archive_date_from == "2006-11-08"
        assert ant.archive_date_to == "2019-07-02"
        assert ant.dates_from_station_info
        text = format_triage(r)
        assert "2006-06-29 → 2019-09-24" in text
        assert "archive saw 2006-11-08→2019-07-02" in text

    def test_archive_dates_used_when_no_station_info(self):
        r = reconcile_eras(
            "KOSK",
            KOSK_ARCHIVE,
            KOSK_TOS,
            current_install=KOSK_INSTALL,
            station_id=4356,
            station_info=None,
        )
        ant = next(m for m in r.missing_eras if m.serial == "5923")
        assert ant.date_from == "2006-11-08"  # falls back to archive
        assert not ant.dates_from_station_info
