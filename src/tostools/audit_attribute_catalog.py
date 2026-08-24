"""Reconcile ``data/attribute_codes.yaml`` against the TOS schema.

The catalog is hand-written — every entry carries ``walked: false``, and
nothing ever checked its code names against TOS. It drifted: 64 of its 148
codes name attributes TOS does not define, while codes in daily use are
absent from it entirely. ``close_date`` is the clearest case — the catalog
lists it, TOS calls the same thing ``date_end`` (identical Icelandic label
``Lokadagsetning``, 844 stations), and ``tos search --active-gps`` expands
to a predicate the catalog therefore does not contain.

**Observation cannot settle this.** ``--attribute-list`` aggregates over
``entity["attributes"]``, so a code carried by no station is
indistinguishable from a code that does not exist. The authority is
``GET /admin_attribute_rows`` — the attribute *type* table, one row per
``(code, entity_type)``, independent of which entities carry values. It
needs no credentials.

Two findings, deliberately kept apart because they have different
remedies:

- **phantom** — in the catalog, not in the TOS schema. The catalog is
  wrong; the entry is unreachable and, where a live code carries the same
  Icelandic label, almost certainly a misremembered name for it.
- **unlisted** — defined in TOS and carried by live entities, but absent
  from the catalog. Under ``tosGPS`` these are unreachable: the profile
  gate only admits catalog codes.

Severity follows blast radius, not count. A phantom code that some code
path would try to WRITE is an error; one that merely pollutes the search
vocabulary is a warning. Today every phantom code is in the second class,
because the write paths (``audit_missing_attributes``,
``station.station_required_codes``) all gate on ``gps_required_for`` /
``gps_recommended_for``, and no phantom entry carries one. That is
luck rather than design, so the audit checks it every run instead of
assuming it holds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests

from .api.tos_client import canonical_tos_url
from .audit_attribute_dates import load_catalog_scoped
from .utils.logging import get_logger

logger = get_logger(__name__, logging.WARNING)

#: The attribute-type table. A plain read — no credentials.
SCHEMA_ENDPOINT = "/admin_attribute_rows"

#: The entity-type table, mapping ``id_entity_type`` to a code.
ENTITY_TYPE_ENDPOINT = "/admin_entity_type_rows"

#: Catalog scopes, in report order.
SCOPES = ("stations", "devices", "locations")

#: Catalog scope → the TOS entity-type code(s) it covers.
#:
#: TOS keys an attribute by ``(code, id_entity_type)``, not by code alone —
#: ``_resolve_id_attribute`` says so ("multiple rows per code, one per
#: entity_type"). Bare membership therefore passes a catalog entry whose
#: code TOS defines only for some OTHER entity type, which is exactly the
#: error this verb exists to catch.
#:
#: ``devices`` spans two entity types: the catalog's devices scope holds
#: ``monument`` alongside the GNSS hardware, and a monument is Innviði —
#: entity type ``infrastructure``, not ``device``.
SCOPE_ENTITY_TYPES = {
    "stations": ("station",),
    "devices": ("device", "infrastructure"),
    "locations": ("location",),
}

#: Fields that make a catalog entry reachable by a code path that WRITES.
#: A phantom code carrying any of these would propose a TOS write for an
#: attribute TOS cannot accept — `_resolve_id_attribute` would raise
#: "unknown attribute code" at the boundary.
WRITE_REACHING_FIELDS = (
    "gps_required_for",
    "gps_required_when_installed",
    "gps_recommended_for",
)


@dataclass
class PhantomCode:
    """A catalog entry naming an attribute TOS does not define."""

    scope: str
    code: str
    label: Optional[str] = None
    gps_relevant: bool = False
    #: Non-empty when a write path could reach it — an error, not a warning.
    write_reaching: List[str] = field(default_factory=list)
    #: Live codes sharing this entry's Icelandic label — the rename candidate.
    same_label_as: List[str] = field(default_factory=list)
    #: True when TOS defines the code, but only for some OTHER entity type.
    #: A subtler error than an invented name: the code is real, the scope is
    #: wrong, and bare code membership would have called it fine.
    wrong_scope: bool = False
    #: Entity-type codes TOS does define it for, when ``wrong_scope``.
    defined_for: List[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        if self.write_reaching:
            return "error"
        return "warning" if self.gps_relevant else "info"


@dataclass
class UnlistedCode:
    """A TOS attribute the catalog never mentions."""

    code: str
    label: Optional[str] = None
    entity_types: List[Any] = field(default_factory=list)


@dataclass
class CatalogAuditReport:
    """Everything the CLI renders, plus the counts that decide the exit code."""

    phantom: List[PhantomCode] = field(default_factory=list)
    unlisted: List[UnlistedCode] = field(default_factory=list)
    catalog_codes: int = 0
    schema_codes: int = 0
    catalog_path: Optional[str] = None

    @property
    def errors(self) -> List[PhantomCode]:
        return [p for p in self.phantom if p.severity == "error"]

    @property
    def has_findings(self) -> bool:
        return bool(self.phantom or self.unlisted)


def fetch_schema_codes(
    server: str = "vi-api.vedur.is", port: int = 443, timeout: int = 30
) -> Dict[str, Dict[str, Any]]:
    """``{code: {"label": name_is, "entity_types": [...]}}`` from TOS.

    One row per ``(code, entity_type)``, so a code spanning scopes (``model``
    is defined for devices AND monuments) collapses to one entry carrying
    every entity type it is defined for. ``entity_types`` holds entity-type
    *codes* (``station``, ``device``, …) rather than the raw integer ids, so
    the caller never has to know that stations are 2 and devices are 4.

    A row whose ``id_entity_type`` is None is a cross-scope entry (rare, but
    ``_resolve_id_attribute`` rule 2 relies on it); it is recorded as
    ``None`` and satisfies every scope.
    """
    base = f"{'https' if port == 443 else 'http'}://{server}:{port}/tos/internal"

    et_resp = requests.get(
        canonical_tos_url(base, ENTITY_TYPE_ENDPOINT), timeout=timeout
    )
    et_resp.raise_for_status()
    et_names = {
        row.get("id"): row.get("code") for row in et_resp.json() or [] if row.get("id")
    }

    resp = requests.get(canonical_tos_url(base, SCHEMA_ENDPOINT), timeout=timeout)
    resp.raise_for_status()
    out: Dict[str, Dict[str, Any]] = {}
    for row in resp.json() or []:
        code = row.get("code")
        if not code:
            continue
        entry = out.setdefault(code, {"label": row.get("name_is"), "entity_types": []})
        et_id = row.get("id_entity_type")
        name = None if et_id is None else et_names.get(et_id, et_id)
        if name not in entry["entity_types"]:
            entry["entity_types"].append(name)
    return out


def _defined_for_scope(entry: Dict[str, Any], scope: str) -> bool:
    """Is this schema entry defined for the entity type(s) ``scope`` covers?

    A ``None`` entity type is cross-scope and satisfies any scope. An unknown
    scope (a catalog key we have no mapping for) is treated as satisfied —
    reporting every one of its codes as wrongly-scoped would be noise about
    our own mapping, not about the catalog.
    """
    wanted = SCOPE_ENTITY_TYPES.get(scope)
    if wanted is None:
        return True
    types = entry.get("entity_types") or []
    return any(t is None or t in wanted for t in types)


def _label_index(schema: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """``{icelandic_label: [code, ...]}`` over the live schema."""
    idx: Dict[str, List[str]] = {}
    for code, entry in schema.items():
        label = (entry.get("label") or "").strip()
        if label:
            idx.setdefault(label, []).append(code)
    return idx


def audit_attribute_catalog(
    schema: Dict[str, Dict[str, Any]],
    *,
    catalog_path: Optional[Path] = None,
    observed_codes: Optional[Set[str]] = None,
) -> CatalogAuditReport:
    """Compare the catalog against the TOS attribute-type table.

    ``observed_codes`` narrows the *unlisted* half to codes some live entity
    actually carries — without it, every schema code the catalog omits is
    reported, including the ~90 that belong to other disciplines entirely
    and which this catalog has no business listing.
    """
    scoped = load_catalog_scoped(catalog_path)
    by_label = _label_index(schema)
    report = CatalogAuditReport(
        schema_codes=len(schema),
        catalog_path=str(catalog_path) if catalog_path else None,
    )

    catalog_all: Set[str] = set()
    for scope in SCOPES:
        entries = scoped.get(scope) or {}
        for code, entry in sorted(entries.items()):
            catalog_all.add(code)
            schema_entry = schema.get(code)
            # Scope-aware, not bare membership: TOS keys by (code,
            # entity_type), so a code defined only for some other entity type
            # is still wrong here — just wrong in a subtler way.
            in_scope = schema_entry is not None and _defined_for_scope(
                schema_entry, scope
            )
            if in_scope:
                continue
            entry = entry or {}
            label = (entry.get("icelandic_label") or "").strip() or None
            report.phantom.append(
                PhantomCode(
                    scope=scope,
                    code=code,
                    label=label,
                    gps_relevant=entry.get("gps_relevance") == "yes",
                    write_reaching=[f for f in WRITE_REACHING_FIELDS if entry.get(f)],
                    # Same label, different name — how a rename announces itself.
                    same_label_as=sorted(by_label.get(label, [])) if label else [],
                    wrong_scope=schema_entry is not None,
                    defined_for=(
                        [str(t) for t in (schema_entry.get("entity_types") or [])]
                        if schema_entry is not None
                        else []
                    ),
                )
            )
    report.catalog_codes = len(catalog_all)

    for code in sorted(set(schema) - catalog_all):
        if observed_codes is not None and code not in observed_codes:
            continue
        report.unlisted.append(
            UnlistedCode(
                code=code,
                label=schema[code].get("label"),
                entity_types=schema[code].get("entity_types") or [],
            )
        )
    return report
