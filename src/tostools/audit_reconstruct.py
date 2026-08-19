"""Reconstruct a station's device history from the cold RINEX archive.

The deterministic core behind ``tos audit reconstruct-from-archive``. It takes
the empirical hardware eras (from :func:`tostools.audit_rinex_timeline.run_rinex_timeline`,
receiver + antenna) and the station's current TOS child joins, and produces a
triage a human reviews before ``tos audit apply``.

It composes the tools the fleet already has rather than re-deriving them:

* **join-date fixes** — an OPEN TOS join whose ``time_from`` predates the
  archive's current-unit install is backdated metadata (KOSK/ISAK class).
  Emitted as ``patch-join-date`` — the deterministic fix ``verify-from-rinex``
  already emits for receivers, here also for antennas. UNCOMMENTED.

* **missing eras, gated through the serial dup-guard** — an archive era whose
  serial matches no TOS join is a gap. But whether to *create* a device or
  *adopt* an existing one is exactly what :func:`device_find.find_devices_by_serial`
  resolves. A ``reopen`` bucket (device exists, detached) yields a real
  ``create-join`` line; ``create`` (serial provably absent) stays REVIEW prose;
  ``attached`` / ``duplicate`` / ``inconclusive`` surface the dup-guard's own
  guidance. This stops the verb ever advising a duplicate mint.

* **station.info enrichment** — the archive header carries what the receiver
  *wrote*; GAMIT station.info carries the *curated* type + the composite ARP
  height. Injected occupations annotate each missing era with the canonical
  model and the composite height (which still needs the monument split — the
  ISAK ARP-retraction lesson, surfaced as a REVIEW note).

* **companion audits** — the attribute dimension (missing-attributes,
  attribute-dates, firmware-chain) is a separate pass; the triage ends with the
  exact follow-up commands for this station so the operator runs them next.

The module is pure (no HTTP, no argparse, no file walk): the runner injects the
archive segments, the TOS joins, a ``serial_lookup`` callable, and parsed
station.info occupations, so the reconciliation logic is unit-testable against a
station's known-correct answer key (KOSK is the first such fixture).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Optional

from .device import is_synthetic_serial

# Subtypes this reconstruction reasons about, in emit order.
RECEIVER = "gnss_receiver"
ANTENNA = "antenna"

#: How far station.info's curated install date may lead the archive's first
#: archived day before the two are treated as disagreeing rather than as a
#: startup gap.
#:
#: The gap is real and expected: a unit is installed, then data starts flowing.
#: KOSK is the calibration point at the small end — station.info 2019-09-24 vs
#: archive 2019-09-25, one day, which must stay silent. VMEY is the calibration
#: point at the large end — station.info claims the antenna from 2022-06-12
#: while the archive (and TOS, and vitjun 4007) put it at 2023-01-11, 213 days
#: later. A month is generously above any plausible commissioning delay and an
#: order of magnitude below a curation error.
STATION_INFO_DIVERGENCE_TOLERANCE_DAYS = 31

#: Serial values that exist to fill a required field, not to identify a unit.
#: ``0000`` is the fleet's RINEX convention for an antenna whose factory serial
#: was never recorded; ``000000`` is GAMIT station.info's. Neither can be
#: matched against TOS, so an era carrying one has to be placed by its dates.
_PLACEHOLDER_SERIALS = frozenset({"UNKNOWN", "NONE", "N/A", "-"})

# Serial dup-guard buckets (mirror tostools.device_find). "reopen" is the only
# one that yields an automatic create-join; the rest need a human's eyes.
BUCKET_CREATE = "create"
BUCKET_REOPEN = "reopen"
BUCKET_ATTACHED = "attached"
BUCKET_DUPLICATE = "duplicate"
BUCKET_INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ArchiveEra:
    """One hardware occupation as the archive records it."""

    subtype: str  # RECEIVER | ANTENNA
    model: Optional[str]
    serial: Optional[str]
    date_from: str  # ISO date (first archived day of the era)
    date_to: str  # ISO date (last archived day of the era)


@dataclass(frozen=True)
class TosJoin:
    """One TOS child join (device ↔ station), open or closed."""

    child_id: int
    id_connection: int
    subtype: str
    serial: Optional[str]
    time_from: str
    time_to: Optional[str]  # None when open

    @property
    def is_open(self) -> bool:
        return self.time_to is None


@dataclass(frozen=True)
class SerialHit:
    """Result of the serial dup-guard for one era's serial (injected).

    Adapted by the runner from :class:`device_find.SerialLookup`.
    """

    bucket: str  # BUCKET_* constant
    entity_id: Optional[int]  # the resolved entity (reopen/attached)
    parent: Optional[str]  # its current/last parent, for context
    summary: str  # the dup-guard's own one-line guidance


@dataclass(frozen=True)
class StationInfoEra:
    """One curated occupation from GAMIT station.info (injected)."""

    subtype: str  # RECEIVER | ANTENNA
    model: Optional[str]
    serial: Optional[str]
    date_from: str
    date_to: Optional[str]
    composite_height: Optional[str] = None  # station.info Ant Ht (antenna only)


@dataclass(frozen=True)
class JoinFix:
    """A backdated OPEN join to correct to the archive's install date."""

    child_id: int
    id_connection: int
    subtype: str
    serial: Optional[str]
    tos_time_from: str
    archive_install: str
    #: False when the install date could not be corroborated — station.info and
    #: the archive disagreed beyond
    #: :data:`STATION_INFO_DIVERGENCE_TOLERANCE_DAYS`. Such a fix is emitted
    #: COMMENTED: "uncommented" means archive-proven, and a date two authorities
    #: contradict each other about is not proven by either.
    archive_proven: bool = True

    def action_line(self) -> str:
        prefix = "ACTION" if self.archive_proven else "#ACTION"
        return (
            f"{prefix} {self.child_id} patch-join-date "
            f"{self.id_connection} time_from {self.archive_install}"
            f"  # was {self.tos_time_from} ({self.subtype}"
            f"{'' if self.serial is None else f' sn={self.serial}'})"
        )


@dataclass(frozen=True)
class MissingEra:
    """An archive era with no matching TOS join, classified by the dup-guard."""

    subtype: str
    model: Optional[str]
    serial: Optional[str]
    date_from: str
    date_to: str
    # dup-guard classification (None when serial_lookup was not run):
    bucket: Optional[str] = None
    adopt_entity_id: Optional[int] = None  # set → emit create-join (reopen)
    lookup_summary: Optional[str] = None
    # station.info enrichment:
    canonical_model: Optional[str] = None
    composite_height: Optional[str] = None
    # date provenance: date_from/date_to are the EFFECTIVE (preferred) bounds;
    # archive_* keep what the archive saw so the triage can show a divergence.
    archive_date_from: Optional[str] = None
    archive_date_to: Optional[str] = None
    dates_from_station_info: bool = False

    @property
    def is_adopt(self) -> bool:
        return self.bucket == BUCKET_REOPEN and self.adopt_entity_id is not None


@dataclass(frozen=True)
class ReconstructReport:
    station: str
    station_id: Optional[int] = None
    join_fixes: List[JoinFix] = field(default_factory=list)
    missing_eras: List[MissingEra] = field(default_factory=list)
    review: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (self.join_fixes or self.missing_eras or self.review)


def _norm_serial(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip().upper()
    return s or None


def is_placeholder_serial(s: Optional[str]) -> bool:
    """True when ``s`` fills a serial field without identifying a unit.

    Covers the empty value, the all-zero conventions (RINEX ``0000``, GAMIT
    ``000000``), the literal unknowns, and TOS's synthetic
    ``<subtype>-<STID>-<YYYYMMDD>`` sentinels — including the field-truncated
    form, which is why :func:`tostools.device.is_synthetic_serial` had to learn
    about truncation first.

    A placeholder must never be compared against a TOS serial: doing so reports
    a device that IS recorded as missing, and invites minting a duplicate. VMEY
    is the worked example — the archive carries ``0000`` for the same antenna
    TOS holds as ``antenna-VMEY-20230111``.
    """
    ns = _norm_serial(s)
    if ns is None:
        return True
    if ns in _PLACEHOLDER_SERIALS:
        return True
    if set(ns) == {"0"}:  # 0, 0000, 000000 — any all-zero run
        return True
    return is_synthetic_serial(ns)


def _days_between(a: str, b: str) -> int:
    """Absolute day count between two ISO dates; ``-1`` when either won't parse."""
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (TypeError, ValueError):
        return -1


def _unit_key(era: StationInfoEra) -> tuple:
    """The identity of the physical unit a station.info row describes."""
    return (_norm_serial(era.serial), (era.model or "").strip().upper() or None)


def _join_contains(join: TosJoin, era: ArchiveEra) -> bool:
    """Does ``join``'s window fully contain ``era``'s? Open ``time_to`` = +inf."""
    j_to = (join.time_to or "9999-12-31")[:10]
    return join.time_from[:10] <= era.date_from[:10] and era.date_to[:10] <= j_to


def _overlaps(a_from: str, a_to: Optional[str], b_from: str, b_to: Optional[str]) -> bool:
    """Do two [from, to] date windows overlap? Open (None) to == +infinity."""
    a_to = a_to or "9999-12-31"
    b_to = b_to or "9999-12-31"
    return a_from[:10] <= b_to[:10] and b_from[:10] <= a_to[:10]


def _match_station_info(
    station_info: Optional[List[StationInfoEra]], era: ArchiveEra
) -> Optional[StationInfoEra]:
    """Find the station.info occupation covering an archive era.

    Prefer an exact serial match; fall back to the same-subtype occupation whose
    window overlaps the era (serials in station.info and RINEX headers sometimes
    differ in formatting).
    """
    if not station_info:
        return None
    same = [s for s in station_info if s.subtype == era.subtype]
    for s in same:
        if _norm_serial(s.serial) and _norm_serial(s.serial) == _norm_serial(era.serial):
            return s
    for s in same:
        if _overlaps(era.date_from, era.date_to, s.date_from, s.date_to):
            return s
    return None


def _open_station_info_era(
    station_info: Optional[List[StationInfoEra]], subtype: str
) -> Optional[StationInfoEra]:
    """The station.info row that STARTS the current unit's occupation run.

    Not the last row — the *first* row of the contiguous run of rows carrying
    the same unit for this subtype. A station.info occupation is split by ANY
    metadata change on the line (firmware, antenna height, the *other* device),
    so the open row's ``date_from`` is the last time something changed, which is
    only the install date when nothing has changed since.

    VMEY is why this matters. Its open row starts 2022-06-12 because the antenna
    changed; receiver ``3018426`` runs unbroken across that boundary from
    2017 doy 192. Reading the open row's date gave the receiver an install date
    five years late — and since a backdated-join fix is emitted UNCOMMENTED, the
    verb proposed corrupting a join that was already correct.
    """
    if not station_info:
        return None
    same = sorted(
        (s for s in station_info if s.subtype == subtype), key=lambda s: s.date_from
    )
    open_idx = next(
        (i for i in range(len(same) - 1, -1, -1) if same[i].date_to is None), None
    )
    if open_idx is None:
        return None
    key = _unit_key(same[open_idx])
    start = open_idx
    while start > 0 and _unit_key(same[start - 1]) == key:
        start -= 1
    return same[start]


def reconcile_eras(
    station: str,
    archive_eras: List[ArchiveEra],
    tos_joins: List[TosJoin],
    *,
    current_install: dict,
    station_id: Optional[int] = None,
    serial_lookup: Optional[Callable[[str, str], Optional[SerialHit]]] = None,
    station_info: Optional[List[StationInfoEra]] = None,
    joinfix_subtypes=(RECEIVER, ANTENNA),
) -> ReconstructReport:
    """Reconcile the archive's hardware eras against TOS's child joins.

    Args:
        station / station_id: marker + TOS id (for the create-join parent).
        archive_eras: every receiver + antenna occupation from the archive.
        tos_joins: every TOS receiver + antenna join (open and closed).
        current_install: ``{subtype: iso_date}`` — archive current-unit install.
        serial_lookup: ``(serial, subtype) -> SerialHit`` dup-guard (injected;
            the runner wraps :func:`device_find.find_devices_by_serial`). When
            ``None``, missing eras are reported without adopt/create resolution.
        station_info: parsed GAMIT occupations for enrichment (injected).
        joinfix_subtypes: which subtypes to emit join-date fixes for. The runner
            passes a subset when a subtype's fix is sourced elsewhere (e.g. the
            receiver from ``verify-from-rinex``); missing-era detection always
            covers both.
    """
    report = ReconstructReport(station=station.upper(), station_id=station_id)

    # --- 1. Backdated OPEN joins → patch-join-date ------------------------
    # station.info's curated install date is preferred over the archive's
    # first-data day: the archive only knows when bytes exist, so a startup gap
    # makes it lag the real install (KOSK: archive 2019-09-25 vs station.info
    # 2019-09-24). Divergence is surfaced as a REVIEW note.
    for subtype in joinfix_subtypes:
        archive_install = current_install.get(subtype)
        si_open = _open_station_info_era(station_info, subtype)
        install = archive_install
        proven = True

        if si_open:
            si_date = si_open.date_from[:10]
            if not archive_install:
                install = si_date
            else:
                delta = _days_between(si_date, archive_install)
                if delta == 0:
                    pass  # authorities agree; archive value already in `install`
                elif 0 < delta <= STATION_INFO_DIVERGENCE_TOLERANCE_DAYS:
                    # A commissioning gap: the unit was installed, then data
                    # started. station.info's curated date is the better one.
                    install = si_date
                    report.review.append(
                        f"{subtype} install date: using station.info {si_date} "
                        f"(archive first-data {archive_install[:10]}, {delta}d "
                        f"apart) — attribute date_from values should match the "
                        f"join."
                    )
                else:
                    # Too far apart to be a startup gap. Fall back to the
                    # archive — it is the only one of the two that is evidence
                    # rather than curation — and refuse to emit an uncommented
                    # action off a date the authorities contradict.
                    proven = False
                    report.review.append(
                        f"{subtype} install date DISPUTED: station.info says "
                        f"{si_date}, the archive {archive_install[:10]} "
                        f"({delta}d apart — beyond the "
                        f"{STATION_INFO_DIVERGENCE_TOLERANCE_DAYS}d startup-gap "
                        f"tolerance). Using the archive and COMMENTING any join "
                        f"fix below. Resolve against the vitjun record before "
                        f"applying: station.info rows split on any metadata "
                        f"change, so a stale one can misdate a whole era."
                    )
        if not install:
            continue
        for j in [j for j in tos_joins if j.subtype == subtype and j.is_open]:
            if j.time_from[:10] < install[:10]:
                report.join_fixes.append(
                    JoinFix(
                        child_id=j.child_id,
                        id_connection=j.id_connection,
                        subtype=subtype,
                        serial=j.serial,
                        tos_time_from=j.time_from[:10],
                        archive_install=install[:10],
                        archive_proven=proven,
                    )
                )

    # --- 2. Archive eras with no TOS device, gated through the dup-guard --
    tos_serials = {_norm_serial(j.serial) for j in tos_joins if _norm_serial(j.serial)}
    seen_missing: set = set()
    for era in archive_eras:
        ns = _norm_serial(era.serial)
        placeholder = is_placeholder_serial(era.serial)

        if placeholder:
            # No identity to compare, so place the era by its dates instead. A
            # TOS join of the same subtype whose window CONTAINS the era already
            # accounts for it — that is the ordinary case (VMEY's archive says
            # `0000` for the antenna TOS holds as `antenna-VMEY-20230111`).
            # Containment, not mere overlap: a partial overlap means the era
            # crosses a swap boundary and a human should look.
            if any(
                j.subtype == era.subtype and _join_contains(j, era) for j in tos_joins
            ):
                continue
            key = (era.subtype, "<placeholder>", era.date_from[:10])
        else:
            if ns in tos_serials:
                continue
            key = (era.subtype, ns)

        if key in seen_missing:
            continue
        seen_missing.add(key)

        # A placeholder tells the dup-guard nothing and costs a ~110s fleet walk
        # per serial, so don't spend one on it.
        hit = (
            serial_lookup(era.serial, era.subtype)
            if (serial_lookup and ns and not placeholder)
            else None
        )
        si = _match_station_info(station_info, era)
        # Prefer station.info's curated era bounds — the archive's last-data day
        # can fall short of the real removal after an end-of-life gap (KOSK:
        # archive 2019-07-02 vs station.info 2019-09-24).
        eff_from = si.date_from[:10] if si else era.date_from
        eff_to = (si.date_to[:10] if (si and si.date_to) else era.date_to)
        report.missing_eras.append(
            MissingEra(
                subtype=era.subtype,
                model=era.model,
                serial=era.serial,
                date_from=eff_from,
                date_to=eff_to,
                bucket=hit.bucket if hit else None,
                adopt_entity_id=(hit.entity_id if hit and hit.bucket == BUCKET_REOPEN else None),
                lookup_summary=hit.summary if hit else None,
                canonical_model=si.model if si else None,
                composite_height=si.composite_height if si else None,
                archive_date_from=era.date_from,
                archive_date_to=era.date_to,
                dates_from_station_info=bool(si),
            )
        )

    # --- 3. Non-deterministic residue → review prose ---------------------
    if any(e.subtype == ANTENNA for e in report.missing_eras) or any(
        f.subtype == ANTENNA for f in report.join_fixes
    ):
        report.review.append(
            "Antenna heights are STATION COMPOSITES (monument_height + ARP delta). "
            "Split before writing antenna_height: the antenna carries the ARP delta "
            "above the monument, the monument carries the rest. See the ISAK "
            "ARP-retraction lesson."
        )

    return report


def format_triage(
    report: ReconstructReport,
    *,
    apply_path: str = "<file>",
    station_info_path: Optional[str] = None,
) -> str:
    """Render a :class:`ReconstructReport` as a ``tos audit apply`` triage file.

    Deterministic ``patch-join-date`` lines are UNCOMMENTED; a dup-guard-proven
    adopt emits a commented ``create-join`` (the operator confirms dates); every
    other missing-era class and the composite split stay commented REVIEW prose.
    A companion-audits footer names the attribute-dimension next steps.
    """
    st = report.station
    L: List[str] = []
    L.append("# === tos audit reconstruct-from-archive — triage action file ===")
    L.append(f"# Station: {st}" + (f" (id_entity={report.station_id})" if report.station_id else ""))
    L.append("#")
    L.append("# Deterministic join-date fixes are UNCOMMENTED (archive-proven).")
    L.append("# create-join adopts are COMMENTED (serial dup-guard found the entity;")
    L.append("# confirm the dates). Everything else is REVIEW prose.")
    L.append("#")
    L.append(f"#   tos audit apply {apply_path}          # dry-run preview")
    L.append(f"#   tos audit apply {apply_path} --apply  # commit writes")
    L.append("")

    if report.is_clean:
        L.append("# (archive and TOS agree — nothing to reconstruct)")
        L.append("")
        return "\n".join(L)

    proven_fixes = [f for f in report.join_fixes if f.archive_proven]
    disputed_fixes = [f for f in report.join_fixes if not f.archive_proven]

    if proven_fixes:
        L.append("# --- backdated open joins (current unit predates its archive) ---")
        for fix in proven_fixes:
            L.append(fix.action_line())
        L.append("")

    if disputed_fixes:
        L.append("# --- DISPUTED install dates — COMMENTED, do not apply blind ---")
        L.append("# station.info and the archive disagree by more than a startup")
        L.append("# gap, so neither proves this date. See the REVIEW notes below,")
        L.append("# check the vitjun record, then uncomment if the date holds.")
        for fix in disputed_fixes:
            L.append(fix.action_line())
        L.append("")

    # Adopts the dup-guard proved (reopen a detached existing entity).
    adopts = [m for m in report.missing_eras if m.is_adopt]
    if adopts:
        L.append("# --- adopt existing detached devices (dup-guard: reopen) ---")
        L.append("# The serial already exists in TOS, detached. create-join re-attaches")
        L.append("# it to this station for its archived era. Confirm the dates.")
        for m in adopts:
            parent = f"{report.station_id}" if report.station_id else "<station_id>"
            model = m.canonical_model or m.model or "?"
            L.append(
                f"#   {m.subtype} {model} sn={m.serial}  ({m.date_from} → {m.date_to})"
                + (f"  [station.info h={m.composite_height} — split by monument]"
                   if m.composite_height else "")
            )
            L.append(
                f"#ACTION {m.adopt_entity_id} create-join {parent} "
                f"{m.date_from} {m.date_to}"
            )
        L.append("")

    # Everything else needs a human before any write.
    others = [m for m in report.missing_eras if not m.is_adopt]
    if others:
        L.append("# " + "=" * 70)
        L.append("# REVIEW — missing eras that are NOT a clean adopt")
        L.append("# " + "=" * 70)
        for m in others:
            model = m.canonical_model or m.model or "?"
            h = f"  station.info h={m.composite_height}" if m.composite_height else ""
            arch = ""
            if m.dates_from_station_info and (
                (m.archive_date_from or "")[:10] != m.date_from[:10]
                or (m.archive_date_to or "")[:10] != m.date_to[:10]
            ):
                arch = (
                    f"  [station.info dates; archive saw "
                    f"{m.archive_date_from}→{m.archive_date_to}]"
                )
            L.append(
                f"#   MISSING {m.subtype}: {model} sn={m.serial} "
                f"{m.date_from} → {m.date_to}{h}{arch}"
            )
            if m.bucket == BUCKET_CREATE:
                L.append("#     → dup-guard: serial provably absent → create-device, then join.")
                L.append("#       Copy-paste (fill <WAREHOUSE>; note the new id_entity, then uncomment the join):")
                parent = f"{report.station_id}" if report.station_id else "<station_id>"
                model = m.canonical_model or m.model or "<model>"
                if m.subtype == RECEIVER:
                    L.append(
                        f"#   receivers cfg add-receiver --location '<WAREHOUSE>' "
                        f"--serial {m.serial} --model '{model}' "
                        f"--date-start {m.date_from} --no-dry-run"
                    )
                else:
                    ht = (
                        f" --antenna-height <SPLIT_OF_{m.composite_height}>"
                        if m.composite_height else ""
                    )
                    L.append(
                        f"#   receivers cfg add-antenna --warehouse '<WAREHOUSE>' "
                        f"--serial {m.serial} --model '{model}'{ht} "
                        f"--date-start {m.date_from} --no-dry-run"
                    )
                L.append(
                    f"#   #ACTION <new_id> create-join {parent} "
                    f"{m.date_from} {m.date_to}"
                )
            elif m.bucket == BUCKET_ATTACHED:
                L.append(f"#     → dup-guard: {m.lookup_summary} (attached elsewhere — verify, don't duplicate)")
            elif m.bucket in (BUCKET_DUPLICATE, BUCKET_INCONCLUSIVE):
                L.append(f"#     → dup-guard: {m.lookup_summary}")
            elif m.bucket is None:
                L.append("#     → serial dup-guard not run (--no-serial-lookup); classify by hand")
        L.append("")

    if report.review:
        L.append("# --- REVIEW notes -------------------------------------------------")
        for note in report.review:
            L.append(f"#   - {note}")
        L.append("")

    # Companion audits — the attribute dimension is a separate, later pass.
    si = station_info_path or "<station.info>"
    lo = st.lower()
    L.append("# --- companion audits (attribute dimension — run AFTER joins are fixed) ---")
    L.append(f"#   tos audit missing-attributes {st} --history --station-info {si} \\")
    L.append(f"#       --triage {lo}/{lo}_attrs.txt")
    L.append(f"#   tos audit attribute-dates {st}          # 2014-10-17 bulk-load artifacts")
    L.append(f"#   tos audit firmware-chain {st}           # receiver firmware history")
    L.append("")

    return "\n".join(L)
