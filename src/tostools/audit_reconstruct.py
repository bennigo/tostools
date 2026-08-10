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
from typing import Callable, List, Optional

# Subtypes this reconstruction reasons about, in emit order.
RECEIVER = "gnss_receiver"
ANTENNA = "antenna"

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

    def action_line(self) -> str:
        return (
            f"ACTION {self.child_id} patch-join-date "
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
    """The OPEN (current) station.info occupation for a subtype, if any.

    The curated install date of the currently-installed unit — preferred over
    the archive's first-data day for the backdated-join fix.
    """
    if not station_info:
        return None
    open_eras = [s for s in station_info if s.subtype == subtype and s.date_to is None]
    return max(open_eras, key=lambda s: s.date_from) if open_eras else None


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
        install = si_open.date_from if si_open else archive_install
        if not install:
            continue
        if (
            si_open
            and archive_install
            and si_open.date_from[:10] != archive_install[:10]
        ):
            report.review.append(
                f"{subtype} install date: using station.info "
                f"{si_open.date_from[:10]} (archive first-data "
                f"{archive_install[:10]}) — attribute date_from values should "
                f"match the join."
            )
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
                    )
                )

    # --- 2. Archive eras with no TOS device, gated through the dup-guard --
    tos_serials = {_norm_serial(j.serial) for j in tos_joins if _norm_serial(j.serial)}
    seen_missing: set = set()
    for era in archive_eras:
        ns = _norm_serial(era.serial)
        if ns in tos_serials or ns in seen_missing:
            continue
        seen_missing.add(ns)

        hit = serial_lookup(era.serial, era.subtype) if (serial_lookup and ns) else None
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

    if report.join_fixes:
        L.append("# --- backdated open joins (current unit predates its archive) ---")
        for fix in report.join_fixes:
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
