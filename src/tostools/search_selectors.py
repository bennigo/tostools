"""Selector discovery for ``tos search --selectors``.

Answers the three questions you need answered before you can write a
selector, each asked separately rather than dumped together:

- **what station attributes exist?**   ``--selectors station``
- **what device subtypes exist?**      ``--selectors subtypes``
- **what attributes does X have?**     ``--selectors receiver``

Output is built so it can be **pasted straight into the next command**:
the selector is the first token on every line, exactly as
``tos search`` expects it, and ``--json`` emits a bare array of them.

Two sources, kept distinct because they answer different questions:

- the **catalog** (``data/attribute_codes.yaml``) — what the GPS group
  says an entity SHOULD carry. Instant, offline, opinionated. It covers
  ``gnss_receiver`` / ``antenna`` / ``radome`` / ``monument`` only.
- **observed** (``--observed``) — what the live fleet actually carries,
  from the same device walk the search uses. Slower but complete, and the
  only source for the telemetry subtypes (``modem_gsm``, ``sim_card``,
  ``router``) the catalog says nothing about.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .search import ANY_DEVICE, DEVICE_SUBTYPE_ALIASES, device_in_namespace
from .utils.logging import get_logger

logger = get_logger(__name__, logging.WARNING)

#: What ``--selectors`` accepts besides a device-subtype alias.
TOPIC_STATION = "station"
TOPIC_SUBTYPES = "subtypes"
TOPIC_ALL = "all"
TOPICS = (TOPIC_STATION, TOPIC_SUBTYPES, TOPIC_ALL)


@dataclass
class SelectorEntry:
    """One usable selector plus whatever we can say about it."""

    selector: str
    label: Optional[str] = None
    sources: tuple = ()
    mandatory: bool = False

    def source_note(self) -> str:
        return "+".join(self.sources) if self.sources else ""


@dataclass
class SelectorGroup:
    """A named block of selectors — one section of the output."""

    title: str
    entries: List[SelectorEntry] = field(default_factory=list)
    note: Optional[str] = None


@dataclass(frozen=True)
class Profile:
    """A discipline's slice of the TOS vocabulary.

    ``tos`` is unconstrained; a profile narrows it to one station subtype
    and to the attributes that discipline actually curates, so ``tosGPS``
    cannot silently answer a question about a field nobody maintains for
    GPS. Built from the catalog's own ``gps_relevance`` / ``gps_required_for``
    columns rather than a second hand-kept list.
    """

    name: str
    subtype: str
    station: Dict[str, bool] = field(default_factory=dict)
    devices: Dict[str, Dict[str, bool]] = field(default_factory=dict)

    def allows_station(self, code: str) -> bool:
        return code in self.station

    def allows_device(self, subtype: str, code: str) -> bool:
        if subtype == ANY_DEVICE:
            return any(code in codes for codes in self.devices.values())
        return code in self.devices.get(subtype, {})

    def allows(self, namespace: Optional[str], code: str) -> bool:
        if namespace is None:
            return self.allows_station(code)
        return self.allows_device(namespace, code)

    def mandatory(self, namespace: Optional[str], code: str) -> bool:
        if namespace is None:
            return bool(self.station.get(code))
        if namespace == ANY_DEVICE:
            return any(codes.get(code) for codes in self.devices.values())
        return bool(self.devices.get(namespace, {}).get(code))

    def subtypes(self) -> List[str]:
        """Device subtypes this profile curates anything for."""
        return sorted(s for s, codes in self.devices.items() if codes)


def gps_profile(catalog=None) -> Profile:
    """The GPS discipline's profile, read off the attribute catalog.

    Membership is ``gps_relevance == 'yes'``. Mandatory is a non-empty
    ``gps_required_for`` — which on a station names the entity scope
    (``geophysical``) and on a device names the subtypes the attribute is
    required for, so a code can be mandatory on a receiver and optional on
    an antenna. Verified against the catalog: ``gps_required_for`` never
    appears without ``gps_relevance: yes``, so membership is a superset.
    """
    cat = catalog if catalog is not None else _catalog()

    station: Dict[str, bool] = {}
    for code, entry in (cat.get("stations") or {}).items():
        entry = entry or {}
        if entry.get("gps_relevance") == "yes":
            station[code] = bool(entry.get("gps_required_for"))

    devices: Dict[str, Dict[str, bool]] = {
        subtype: {} for subtype in set(DEVICE_SUBTYPE_ALIASES.values())
    }
    for code, entry in (cat.get("devices") or {}).items():
        entry = entry or {}
        if entry.get("gps_relevance") != "yes":
            continue
        required = set(entry.get("gps_required_for") or [])
        applies = entry.get("applies_to") or entry.get("subtypes_observed") or []
        for subtype in applies:
            if subtype in devices:
                devices[subtype][code] = subtype in required

    return Profile(name="GPS", subtype="GPS stöð", station=station, devices=devices)


def canonical_subtypes() -> List[str]:
    """Distinct canonical device subtypes, alphabetically."""
    return sorted(set(DEVICE_SUBTYPE_ALIASES.values()))


def aliases_for(subtype: str) -> List[str]:
    """Every alias that resolves to ``subtype``, shortest first."""
    found = [a for a, c in DEVICE_SUBTYPE_ALIASES.items() if c == subtype]
    return sorted(found, key=lambda a: (len(a), a))


def resolve_topic(raw: Optional[str]) -> Optional[str]:
    """Normalise a ``--selectors`` argument, or None for the index.

    Returns one of :data:`TOPICS`, or a canonical device subtype. Raises
    ``ValueError`` naming the valid choices when it is none of those.
    """
    if raw is None:
        return None
    topic = raw.strip().lower()
    if not topic:
        return None
    if topic in TOPICS:
        return topic
    if topic in DEVICE_SUBTYPE_ALIASES:
        return DEVICE_SUBTYPE_ALIASES[topic]
    raise ValueError(
        f"unknown --selectors topic {raw!r} — valid: "
        + ", ".join(list(TOPICS) + sorted(set(DEVICE_SUBTYPE_ALIASES)))
    )


# ---------------------------------------------------------------------------
# Catalog source
# ---------------------------------------------------------------------------


def _catalog() -> Dict[str, Dict[str, Dict[str, Any]]]:
    from .audit_attribute_dates import load_catalog_scoped

    return load_catalog_scoped()


def catalog_station_codes(catalog=None) -> Dict[str, Optional[str]]:
    """``{code: icelandic_label}`` for station attributes."""
    cat = catalog if catalog is not None else _catalog()
    return {
        code: (entry or {}).get("icelandic_label")
        for code, entry in (cat.get("stations") or {}).items()
    }


def catalog_device_codes(subtype: str, catalog=None) -> Dict[str, Optional[str]]:
    """``{code: label}`` the catalog assigns to one device subtype.

    Membership is ``applies_to``, falling back to ``subtypes_observed`` —
    32 of the 95 device codes carry no ``applies_to`` at all (they are SIL
    and hydro sensor attributes), so a strict read would silently drop
    anything the catalog never classified.
    """
    cat = catalog if catalog is not None else _catalog()
    out: Dict[str, Optional[str]] = {}
    for code, entry in (cat.get("devices") or {}).items():
        entry = entry or {}
        applies = entry.get("applies_to") or entry.get("subtypes_observed") or []
        if subtype in applies:
            out[code] = entry.get("icelandic_label")
    return out


# ---------------------------------------------------------------------------
# Observed source
# ---------------------------------------------------------------------------


def observed_station_codes(stations: List[dict]) -> Dict[str, int]:
    """``{code: station_count}`` actually present in the fleet listing."""
    counts: Dict[str, int] = {}
    for st in stations:
        for code in {a.get("code") for a in st.get("attributes") or []}:
            if code:
                counts[code] = counts.get(code, 0) + 1
    return counts


def observed_device_codes(
    devices_by_id: Dict[int, List[dict]], subtype: str
) -> Dict[str, int]:
    """``{code: device_count}`` seen on devices of ``subtype``."""
    counts: Dict[str, int] = {}
    for devices in devices_by_id.values():
        for d in devices:
            if not device_in_namespace(d, subtype):
                continue
            for code in {a.get("code") for a in d.get("attributes") or []}:
                if code:
                    counts[code] = counts.get(code, 0) + 1
    return counts


def observed_subtypes(devices_by_id: Dict[int, List[dict]]) -> Dict[str, int]:
    """``{subtype: device_count}`` for every joined device seen."""
    counts: Dict[str, int] = {}
    for devices in devices_by_id.values():
        for d in devices:
            st = d.get("subtype")
            if st:
                counts[st] = counts.get(st, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Group builders
# ---------------------------------------------------------------------------


def _merge(
    catalog_codes: Dict[str, Optional[str]],
    observed_counts: Optional[Dict[str, int]],
    prefix: str = "",
) -> List[SelectorEntry]:
    """Union catalog + observed into sorted entries, tagging the source."""
    entries: List[SelectorEntry] = []
    codes = set(catalog_codes) | set(observed_counts or {})
    for code in sorted(codes):
        sources = []
        if code in catalog_codes:
            sources.append("catalog")
        if observed_counts and code in observed_counts:
            sources.append("observed")
        entries.append(
            SelectorEntry(
                selector=f"{prefix}{code}",
                label=catalog_codes.get(code),
                sources=tuple(sources),
            )
        )
    return entries


def _apply_profile(
    entries: List[SelectorEntry],
    profile: Optional[Profile],
    namespace: Optional[str],
) -> List[SelectorEntry]:
    """Drop out-of-profile entries and mark the mandatory ones.

    Mandatory first, then alphabetical — the required set is what you check
    when onboarding a station, so it should not be hunted for in a list.
    """
    if profile is None:
        return entries
    kept = []
    for e in entries:
        code = e.selector.split(".", 1)[1] if namespace else e.selector
        if not profile.allows(namespace, code):
            continue
        if profile.mandatory(namespace, code):
            e = SelectorEntry(
                selector=e.selector,
                label=e.label,
                sources=e.sources,
                mandatory=True,
            )
        kept.append(e)
    kept.sort(key=lambda e: (not e.mandatory, e.selector))
    return kept


def station_group(
    catalog=None,
    observed: Optional[Dict[str, int]] = None,
    profile: Optional[Profile] = None,
) -> SelectorGroup:
    entries = _apply_profile(
        _merge(catalog_station_codes(catalog), observed), profile, None
    )
    title = "station attributes — use bare, e.g. 'iers_domes_number != null'"
    if profile:
        title = (
            f"station attributes — {profile.name}-relevant only "
            f"({len(entries)} of {len(catalog_station_codes(catalog))})"
        )
    return SelectorGroup(title=title, entries=entries)


def subtypes_group(observed: Optional[Dict[str, int]] = None) -> SelectorGroup:
    entries = []
    for subtype in canonical_subtypes():
        alias = aliases_for(subtype)
        shortest = alias[0]
        extra = f"(aliases: {', '.join(alias)})" if len(alias) > 1 else ""
        entries.append(
            SelectorEntry(
                selector=f"{shortest}.",
                label=f"{subtype} {extra}".strip(),
                sources=("observed",) if observed and subtype in observed else (),
            )
        )
    entries.append(SelectorEntry(selector=f"{ANY_DEVICE}.", label="any device subtype"))
    return SelectorGroup(
        title="device subtypes — the namespace before the dot",
        entries=entries,
        note="list one subtype's attributes with: tos search --selectors <subtype>",
    )


def device_group(
    subtype: str,
    catalog=None,
    observed: Optional[Dict[str, int]] = None,
    profile: Optional[Profile] = None,
) -> SelectorGroup:
    alias = aliases_for(subtype)[0]
    cat_codes = catalog_device_codes(subtype, catalog)
    all_entries = _merge(cat_codes, observed, prefix=f"{alias}.")
    entries = _apply_profile(all_entries, profile, subtype)
    title = f"{subtype} attributes — use as '{alias}.<code>'"
    if profile:
        title = (
            f"{subtype} attributes — {profile.name}-relevant only "
            f"({len(entries)} of {len(all_entries)}), use as '{alias}.<code>'"
        )
    group = SelectorGroup(title=title, entries=entries)
    if not entries:
        if profile:
            # --observed cannot help here: it can only add codes, and the
            # profile would filter every one of them out again. Say the
            # real reason instead of sending the reader down that path.
            group.note = (
                f"{subtype} carries no {profile.name}-relevant attributes — "
                f"use plain 'tos search' for the unconstrained vocabulary"
            )
        elif not cat_codes and not observed:
            group.note = (
                f"the catalog classifies no attributes for {subtype} — "
                "re-run with --observed to read them off the live fleet"
            )
    return group
