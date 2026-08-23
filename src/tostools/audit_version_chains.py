"""Audit: does ``software_version`` track ``firmware_version``?

On a Septentrio the two TOS attribute codes are the **same physical
quantity** — ``firmware_version`` (Útgáfa fastbúnaðar) and
``software_version`` (Útgáfa hugbúnaðar). Every writer except
``cfg add-receiver`` touches firmware only, so software drifts, and until
this module existed **nothing compared them**: ``tos station verify``
reported ✓ clean on a chain years stale. The stale value is not cosmetic —
``software_version[:6]`` is the ``SwVer`` column of GAMIT ``station.info``.

Measured 2026-08-22 before the repair: of 103 Septentrio receivers, 49 had
diverged and 8 carried something that was not a firmware value at all.

**The comparison must be PERIOD-AWARE.** The first sweep compared only each
chain's open period and therefore called six stations clean whose history
had diverged (HVEL, ISAK, KALT, NYLA, SENG, THNA) — a tip that happens to
agree proves nothing about the periods behind it.

**Septentrio only.** On Trimble the two codes are genuinely different
quantities (catalog ``sample_values``: ``NP 4.60`` / ``CJ12`` for firmware
versus ``4.60`` / ``-----`` for software), so comparing them there would
manufacture findings. Non-Septentrio receivers are reported as skipped
rather than silently dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .device import firmware_to_software
from .utils.logging import get_logger

logger = get_logger(__name__, logging.WARNING)

FIRMWARE_CODE = "firmware_version"
SOFTWARE_CODE = "software_version"

#: Substrings marking a receiver model as Septentrio, the only family where
#: the two codes are two spellings of one value.
_SEPTENTRIO = ("SEPT", "POLA", "ASTERX")


def is_septentrio(model: Optional[str]) -> bool:
    """Is this receiver model a Septentrio?"""
    m = (model or "").upper()
    return any(tag in m for tag in _SEPTENTRIO)


@dataclass(frozen=True)
class ChainDivergence:
    """One period where the two chains disagree."""

    date_from: Optional[str]
    date_to: Optional[str]
    firmware: Optional[str]
    software: Optional[str]
    expected: Optional[str]
    reason: str

    def describe(self) -> str:
        span = f"{self.date_from or '?'} → {self.date_to or 'open'}"
        return (
            f"{span}  firmware={self.firmware!r} software={self.software!r} "
            f"expected={self.expected!r} ({self.reason})"
        )


@dataclass
class ReceiverChainReport:
    """The two chains of one receiver, compared period for period."""

    id_entity: int
    serial: str
    model: str
    skipped: Optional[str] = None
    divergences: List[ChainDivergence] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.divergences and not self.skipped


@dataclass
class StationVersionChainReport:
    """Every currently-joined receiver of one station."""

    station: str
    station_id: Optional[int]
    receivers: List[ReceiverChainReport] = field(default_factory=list)

    @property
    def violations(self) -> int:
        return sum(len(r.divergences) for r in self.receivers)

    @property
    def clean(self) -> bool:
        return self.violations == 0


def _periods(entity: Dict[str, Any], code: str) -> List[dict]:
    """Every period for ``code``, oldest first, day-granularity."""
    out = []
    for attr in entity.get("attributes") or []:
        if attr.get("code") != code:
            continue
        value = attr.get("value")
        out.append(
            {
                "value": None if value is None else str(value),
                "date_from": (attr.get("date_from") or "")[:10] or None,
                "date_to": (attr.get("date_to") or "")[:10] or None,
            }
        )
    return sorted(out, key=lambda p: p["date_from"] or "")


def compare_chains(firmware: List[dict], software: List[dict]) -> List[ChainDivergence]:
    """Period-for-period comparison of one receiver's two chains.

    The firmware chain is authoritative: the software chain should mirror it
    period for period, each value being :func:`firmware_to_software` of the
    firmware value. Three distinct failures are reported separately, because
    they need different repairs:

    - ``missing``      the software chain has no period covering this one
                       (the VMEY shape — never chained at all)
    - ``value``        boundaries align but the value is wrong (stale, junk,
                       or the right number in the wrong format)
    - ``boundary``     a software period exists but its dates do not match
                       the firmware period it should mirror
    """
    out: List[ChainDivergence] = []
    by_start = {p["date_from"]: p for p in software}

    for fw in firmware:
        expected, warn = firmware_to_software(fw["value"] or "")
        if warn:
            # Firmware itself is malformed — comparing is meaningless, and
            # saying so is more useful than a spurious value mismatch.
            out.append(
                ChainDivergence(
                    fw["date_from"],
                    fw["date_to"],
                    fw["value"],
                    (by_start.get(fw["date_from"]) or {}).get("value"),
                    None,
                    "firmware is not a clean X.Y.Z version",
                )
            )
            continue

        sw = by_start.get(fw["date_from"])
        if sw is None:
            out.append(
                ChainDivergence(
                    fw["date_from"],
                    fw["date_to"],
                    fw["value"],
                    None,
                    expected,
                    "missing",
                )
            )
            continue
        if sw["value"] != expected:
            out.append(
                ChainDivergence(
                    fw["date_from"],
                    fw["date_to"],
                    fw["value"],
                    sw["value"],
                    expected,
                    "value",
                )
            )
        elif sw["date_to"] != fw["date_to"]:
            out.append(
                ChainDivergence(
                    fw["date_from"],
                    fw["date_to"],
                    fw["value"],
                    sw["value"],
                    expected,
                    "boundary",
                )
            )

    # Software periods with no firmware counterpart — orphans left behind by
    # a partial repair, or a chain that outlived its firmware entries.
    fw_starts = {p["date_from"] for p in firmware}
    for sw in software:
        if sw["date_from"] not in fw_starts:
            out.append(
                ChainDivergence(
                    sw["date_from"],
                    sw["date_to"],
                    None,
                    sw["value"],
                    None,
                    "orphan software period (no firmware period starts here)",
                )
            )
    return out


def audit_station_version_chains(
    client: Any,
    name: Optional[str] = None,
    id_entity: Optional[int] = None,
) -> StationVersionChainReport:
    """Compare both version chains on every currently-joined receiver."""
    # Same resolution as every other station audit — marker or id, marker
    # preferred. NOT client.find_station_by_marker, which lives on TOSWriter
    # and is absent from the unauthenticated TOSClient these audits take.
    from .audit import _resolve_station_entity

    sid = (name or "").upper()
    station_id = id_entity
    if station_id is None:
        entity = _resolve_station_entity(client, name=sid, id_entity=None) or {}
        station_id = entity.get("id_entity")
    report = StationVersionChainReport(station=sid, station_id=station_id)
    if not station_id:
        return report

    history = client.get_entity_history(station_id) or {}
    for conn in history.get("children_connections") or []:
        if conn.get("time_to") is not None:
            continue  # closed join — only currently-installed receivers
        child_id = conn.get("id_entity_child")
        if child_id is None:
            continue
        child = client.get_entity_history(int(child_id))
        if not isinstance(child, dict):
            continue
        if child.get("code_entity_subtype") != "gnss_receiver":
            continue

        def _open(code):
            for a in child.get("attributes") or []:
                if a.get("code") == code and not a.get("date_to"):
                    return a.get("value")
            return None

        model = str(_open("model") or "")
        rx = ReceiverChainReport(
            id_entity=int(child_id),
            serial=str(_open("serial_number") or "?"),
            model=model,
        )
        if not is_septentrio(model):
            rx.skipped = (
                f"{model or 'unknown model'}: firmware and software are "
                "genuinely different quantities on this family"
            )
        else:
            rx.divergences = compare_chains(
                _periods(child, FIRMWARE_CODE), _periods(child, SOFTWARE_CODE)
            )
        report.receivers.append(rx)
    return report


def format_report(report: StationVersionChainReport) -> str:
    """Human-readable rendering for the CLI."""
    lines = []
    for rx in report.receivers:
        head = f"  receiver {rx.id_entity} (SN {rx.serial}, {rx.model})"
        if rx.skipped:
            lines.append(f"{head} — skipped: {rx.skipped}")
            continue
        if not rx.divergences:
            lines.append(f"{head} — ✓ chains agree")
            continue
        lines.append(f"{head} — {len(rx.divergences)} divergence(s)")
        lines.extend(f"      {d.describe()}" for d in rx.divergences)
    if not lines:
        lines.append("  no currently-joined receiver")
    return "\n".join(lines)
