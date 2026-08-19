"""A reconstruction must not propose a correction its evidence contradicts.

Two defects, both found on VMEY, both of which made ``tos audit
reconstruct-from-archive`` emit an UNCOMMENTED ``patch-join-date`` that would
have corrupted an already-correct TOS record.

**1. The install date came from the wrong station.info row.** The old code took
the *last open* occupation and used its ``date_from`` as the install date for
every subtype. But a station.info row splits on ANY metadata change on the
line — including a change to the *other* device. VMEY's open row starts
2022-06-12 because the antenna changed; receiver ``3018426`` runs unbroken
across that boundary from 2017 doy 192. The receiver was therefore handed an
install date five years late, against a TOS join that was already right.

**2. There was no divergence gate.** station.info's curated date was preferred
over the archive silently, however far apart they were. The two calibration
points pinned here:

* **KOSK** — station.info 2019-09-24, archive 2019-09-25. One day. A real
  commissioning gap: the unit was installed, then data started. Must stay
  silent and keep preferring station.info.
* **VMEY antenna** — station.info 2022-06-12, archive 2023-01-11. 213 days,
  with TOS and vitjun 4007 both agreeing with the archive. Must fall back to
  the archive and refuse to emit an uncommented action.

The third defect is serial matching: an archive era carrying a placeholder
serial (``0000``, or a field-truncated TOS sentinel) can never match a TOS
serial, so it reported as a MISSING device that is in fact recorded — the
invitation to mint a duplicate.
"""

import pytest

from tostools.audit_reconstruct import (
    ANTENNA,
    RECEIVER,
    STATION_INFO_DIVERGENCE_TOLERANCE_DAYS,
    ArchiveEra,
    StationInfoEra,
    TosJoin,
    format_triage,
    is_placeholder_serial,
    reconcile_eras,
)

# --------------------------------------------------------------------------
# VMEY, as the four authorities actually record it (2026-08-19).
# --------------------------------------------------------------------------

VMEY_ARCHIVE = [
    ArchiveEra(RECEIVER, "TRIMBLE 4000SSI", "28516", "2000-07-27", "2003-11-11"),
    ArchiveEra(RECEIVER, "TRIMBLE 4000SSI", "26093", "2003-11-12", "2012-10-08"),
    ArchiveEra(RECEIVER, "TRIMBLE NETR9", "5211K83153", "2013-10-29", "2017-07-10"),
    ArchiveEra(RECEIVER, "SEPT POLARX5", "3018426", "2017-07-11", "2026-08-18"),
    ArchiveEra(ANTENNA, "TRM29659.00", "148018", "2000-07-27", "2003-11-11"),
    ArchiveEra(ANTENNA, "TRM29659.00", "148018", "2003-11-12", "2022-09-25"),
    # The fleet's "serial never recorded" convention for a RINEX header.
    ArchiveEra(ANTENNA, "SEPCHOKE_B3E6", "0000", "2023-01-11", "2026-08-17"),
    # One day converted while the truncating wheel was still deployed.
    ArchiveEra(
        ANTENNA, "SEPCHOKE_B3E6", "antenna-VMEY-2023011", "2026-08-18", "2026-08-18"
    ),
]

VMEY_TOS = [
    TosJoin(4828, 5920, RECEIVER, "28516", "2000-07-26", "2003-11-11"),
    TosJoin(4824, 5907, RECEIVER, "26093", "2003-11-11", "2013-01-01"),
    TosJoin(4921, 6058, RECEIVER, "5211K83153", "2013-01-01", "2017-07-11"),
    TosJoin(16156, 14011, RECEIVER, "3018426", "2017-07-11", None),
    TosJoin(4504, 5389, ANTENNA, "148018", "2000-07-26", "2023-01-11"),
    TosJoin(19543, 23287, ANTENNA, "antenna-VMEY-20230111", "2023-01-11", None),
]

VMEY_INSTALL = {RECEIVER: "2017-07-11", ANTENNA: "2023-01-11"}


def _si(date_from, date_to, rec_sn, rec_model, ant_sn, ant_model):
    """One station.info occupation, split per subtype as the runner splits it."""
    return [
        StationInfoEra(RECEIVER, rec_model, rec_sn, date_from, date_to),
        StationInfoEra(ANTENNA, ant_model, ant_sn, date_from, date_to, "0.9990"),
    ]


# The five VMEY rows. Note rows 4 and 5 carry the SAME receiver: the boundary
# between them is the antenna swap, not a receiver install.
VMEY_STATION_INFO = (
    _si("2000-07-26", "2003-11-11", "28516", "TRIMBLE 4000SSI", "148018", "TRM29659.00")
    + _si("2003-11-11", "2013-01-01", "26093", "TRIMBLE 4000SSI", "148018", "TRM29659.00")
    + _si("2013-01-01", "2017-07-11", "5211K83153", "TRIMBLE NETR9", "148018", "TRM29659.00")
    + _si("2017-07-11", "2022-02-15", "3018426", "SEPT POLARX5", "148018", "TRM29659.00")
    + _si("2022-06-12", None, "3018426", "SEPT POLARX5", "0000", "SEPCHOKE_B3E6")
)


def _vmey():
    return reconcile_eras(
        "VMEY",
        VMEY_ARCHIVE,
        VMEY_TOS,
        current_install=VMEY_INSTALL,
        station_id=4430,
        station_info=VMEY_STATION_INFO,
    )


class TestVmeyProposesNoWrites:
    """VMEY's joins are correct, so a correct tool must propose nothing."""

    def test_no_join_fix_is_emitted(self):
        # Both open joins already sit on the archive's install date. Every
        # ACTION here would be a regression, not a repair.
        assert _vmey().join_fixes == []

    def test_no_era_reports_as_missing(self):
        assert _vmey().missing_eras == []

    def test_the_triage_contains_no_uncommented_action(self):
        text = format_triage(_vmey())
        offenders = [
            ln for ln in text.splitlines() if ln.startswith("ACTION")
        ]
        assert offenders == [], f"would write to TOS: {offenders}"

    def test_the_disputed_station_info_date_is_still_reported(self):
        # Proposing nothing is not the same as finding nothing: station.info
        # genuinely misdates the antenna, and that stays visible.
        review = " ".join(_vmey().review)
        assert "DISPUTED" in review
        assert "2022-06-12" in review and "2023-01-11" in review


class TestInstallDateComesFromTheUnitsOwnRun:
    def test_receiver_install_walks_back_across_an_antenna_only_split(self):
        # The open row starts 2022-06-12, but the receiver did not change then.
        # Reading the open row gave 2022-06-12 and a bogus fix against a join
        # that was already correct at 2017-07-11.
        assert _vmey().join_fixes == []

    def test_a_backdated_join_is_still_caught(self):
        # The walk-back must not blunt the check it exists to serve.
        tos = [TosJoin(16156, 14011, RECEIVER, "3018426", "2010-01-01", None)]
        rep = reconcile_eras(
            "VMEY", VMEY_ARCHIVE, tos,
            current_install=VMEY_INSTALL, station_info=VMEY_STATION_INFO,
        )
        fixes = [f for f in rep.join_fixes if f.subtype == RECEIVER]
        assert len(fixes) == 1
        assert fixes[0].archive_install == "2017-07-11"
        assert fixes[0].archive_proven is True
        assert fixes[0].action_line().startswith("ACTION ")


class TestDivergenceGate:
    def test_kosk_one_day_gap_keeps_preferring_station_info(self):
        # The commissioning gap the preference was built for. Must stay silent.
        archive = [
            ArchiveEra(RECEIVER, "TRIMBLE NETR9", "5548R50633", "2019-09-25", "2026-08-09")
        ]
        si = [StationInfoEra(RECEIVER, "TRIMBLE NETR9", "5548R50633", "2019-09-24", None)]
        tos = [TosJoin(4835, 5937, RECEIVER, "5548R50633", "2006-11-08", None)]
        rep = reconcile_eras(
            "KOSK", archive, tos,
            current_install={RECEIVER: "2019-09-25"}, station_info=si,
        )
        assert len(rep.join_fixes) == 1
        fix = rep.join_fixes[0]
        assert fix.archive_install == "2019-09-24"  # station.info still wins
        assert fix.archive_proven is True
        assert fix.action_line().startswith("ACTION ")
        assert not any("DISPUTED" in n for n in rep.review)

    def test_a_months_wide_divergence_falls_back_to_the_archive(self):
        archive = [
            ArchiveEra(ANTENNA, "SEPCHOKE_B3E6", "9911", "2023-01-11", "2026-08-17")
        ]
        si = [StationInfoEra(ANTENNA, "SEPCHOKE_B3E6", "9911", "2022-06-12", None)]
        tos = [TosJoin(19543, 23287, ANTENNA, "9911", "2015-01-01", None)]
        rep = reconcile_eras(
            "VMEY", archive, tos,
            current_install={ANTENNA: "2023-01-11"}, station_info=si,
        )
        fix = rep.join_fixes[0]
        assert fix.archive_install == "2023-01-11"  # the archive, not station.info
        assert fix.archive_proven is False
        assert fix.action_line().startswith("#ACTION ")
        assert any("DISPUTED" in n for n in rep.review)

    def test_a_disputed_fix_renders_commented_in_the_triage(self):
        archive = [
            ArchiveEra(ANTENNA, "SEPCHOKE_B3E6", "9911", "2023-01-11", "2026-08-17")
        ]
        si = [StationInfoEra(ANTENNA, "SEPCHOKE_B3E6", "9911", "2022-06-12", None)]
        tos = [TosJoin(19543, 23287, ANTENNA, "9911", "2015-01-01", None)]
        text = format_triage(
            reconcile_eras(
                "VMEY", archive, tos,
                current_install={ANTENNA: "2023-01-11"}, station_info=si,
            )
        )
        assert "DISPUTED" in text
        assert "\n#ACTION 19543 patch-join-date" in text
        assert "\nACTION 19543 patch-join-date" not in text

    @pytest.mark.parametrize(
        "si_date,archive_date,expect_proven",
        [
            ("2019-09-25", "2019-09-25", True),  # identical
            ("2019-09-24", "2019-09-25", True),  # 1 day  — KOSK
            ("2019-08-25", "2019-09-25", True),  # 31 days — on the boundary
            ("2019-08-24", "2019-09-25", False),  # 32 days — over it
            ("2022-06-12", "2023-01-11", False),  # 213 days — VMEY
        ],
    )
    def test_the_boundary_is_where_it_is_documented(
        self, si_date, archive_date, expect_proven
    ):
        assert STATION_INFO_DIVERGENCE_TOLERANCE_DAYS == 31
        archive = [ArchiveEra(RECEIVER, "SEPT POLARX5", "3018426", archive_date, "2026-08-18")]
        si = [StationInfoEra(RECEIVER, "SEPT POLARX5", "3018426", si_date, None)]
        tos = [TosJoin(16156, 14011, RECEIVER, "3018426", "2000-01-01", None)]
        rep = reconcile_eras(
            "X", archive, tos,
            current_install={RECEIVER: archive_date}, station_info=si,
        )
        assert rep.join_fixes[0].archive_proven is expect_proven


class TestACommissioningGapIsNotABackdatedJoin:
    """Install precedes first data by design; a join a few days early is right."""

    def test_a_two_day_gap_proposes_nothing(self):
        # ISAK, live: antenna join 2026-07-30, archive first data 2026-08-01.
        # Moving the join forward to first-data would be the error.
        archive = [
            ArchiveEra(ANTENNA, "TRM159900.00", "2505010005", "2026-08-01", "2026-08-18")
        ]
        tos = [TosJoin(21715, 29351, ANTENNA, "2505010005", "2026-07-30", None)]
        rep = reconcile_eras(
            "ISAK", archive, tos, current_install={ANTENNA: "2026-08-01"}
        )
        assert rep.join_fixes == []

    def test_a_years_wide_gap_still_proposes_the_fix(self):
        # KOSK: the join sat 13 years back, on a receiver replaced in 2019.
        archive = [
            ArchiveEra(RECEIVER, "TRIMBLE NETR9", "5548R50633", "2019-09-25", "2026-08-09")
        ]
        tos = [TosJoin(4835, 5937, RECEIVER, "5548R50633", "2006-11-08", None)]
        rep = reconcile_eras(
            "KOSK", archive, tos, current_install={RECEIVER: "2019-09-25"}
        )
        assert len(rep.join_fixes) == 1
        assert rep.join_fixes[0].archive_proven is True


class TestPlaceholderSerialsArePlacedByDate:
    @pytest.mark.parametrize(
        "value",
        [
            None, "", "0000", "000000", "0",
            "antenna-VMEY-20230111",  # the TOS sentinel
            "antenna-VMEY-2023011",  # the same, truncated by RINEX A20
            "UNKNOWN",
        ],
    )
    def test_recognised_as_non_identifying(self, value):
        assert is_placeholder_serial(value) is True

    @pytest.mark.parametrize("value", ["148018", "3018426", "5211K83153", "28516"])
    def test_a_real_serial_is_left_alone(self, value):
        assert is_placeholder_serial(value) is False

    def test_a_placeholder_era_inside_a_tos_join_is_not_missing(self):
        # The whole VMEY antenna case: archive says 0000, TOS says
        # antenna-VMEY-20230111, same physical antenna.
        assert [m for m in _vmey().missing_eras if m.subtype == ANTENNA] == []

    def test_a_placeholder_era_outside_every_join_is_still_missing(self):
        # Placing by date must not become "never report an antenna".
        archive = [ArchiveEra(ANTENNA, "SEPCHOKE_B3E6", "0000", "2019-01-01", "2020-01-01")]
        tos = [TosJoin(19543, 23287, ANTENNA, "antenna-VMEY-20230111", "2023-01-11", None)]
        rep = reconcile_eras(
            "VMEY", archive, tos, current_install={ANTENNA: "2023-01-11"}
        )
        assert len(rep.missing_eras) == 1
        assert rep.missing_eras[0].serial == "0000"

    def test_a_partial_overlap_is_still_missing(self):
        # Containment, not overlap: an era crossing a swap boundary needs eyes.
        archive = [ArchiveEra(ANTENNA, "SEPCHOKE_B3E6", "0000", "2022-01-01", "2024-01-01")]
        tos = [TosJoin(19543, 23287, ANTENNA, "antenna-VMEY-20230111", "2023-01-11", None)]
        rep = reconcile_eras(
            "VMEY", archive, tos, current_install={ANTENNA: "2023-01-11"}
        )
        assert len(rep.missing_eras) == 1

    def test_two_distinct_placeholder_eras_do_not_collapse(self):
        # Dedup used to key on the serial alone, so every placeholder era after
        # the first vanished regardless of when it ran.
        archive = [
            ArchiveEra(ANTENNA, "A", "0000", "2010-01-01", "2011-01-01"),
            ArchiveEra(ANTENNA, "B", "0000", "2015-01-01", "2016-01-01"),
        ]
        rep = reconcile_eras("X", archive, [], current_install={})
        assert len(rep.missing_eras) == 2

    def test_the_dup_guard_is_not_spent_on_a_placeholder(self):
        # ~110s of fleet walk per serial, for a value that identifies nothing.
        called = []

        def lookup(serial, subtype):
            called.append(serial)
            return None

        archive = [ArchiveEra(ANTENNA, "SEPCHOKE_B3E6", "0000", "2019-01-01", "2020-01-01")]
        reconcile_eras(
            "X", archive, [], current_install={}, serial_lookup=lookup
        )
        assert called == []
