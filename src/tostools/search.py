"""General TOS station search — the engine behind ``tos search``.

Fleet-wide, read-only search over the bulk geophysical station listing
(one bodyless GET — the same endpoint the TOS web UI search uses), with
client-side filtering by:

- **Station attribute predicates** — ``code OP value`` where OP is
  ``=`` / ``!=`` (equality) or ``~`` / ``!~`` (substring), evaluated
  against the station's *currently-open* attribute period (the value
  the TOS UI shows in its Eigindi panel). ``null`` as the value tests
  absence/presence.
- **Device criteria** — ``[TYPE:]MODEL`` specs matched against the
  station's *currently-joined* devices (the TOS UI's Tæki tengd stöð
  panel), with negation forms.

Device data is NOT in the bulk listing — it needs a per-station history
walk (1 + N_children HTTP calls). The pipeline therefore applies the
attribute predicates first (free) and only walks devices for stations
that survive them.

Value normalization is case-insensitive and folds the Icelandic boolean
vocabulary (``já``/``nei``) onto ``true``/``false`` — TOS stores mixed
vocabulary in the wild (RHOF carries ``in_network_epos=true`` but
``is_near_fault_zones=nei``).
"""

from __future__ import annotations

import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .utils.logging import get_logger

logger = get_logger(__name__, logging.WARNING)

# ---------------------------------------------------------------------------
# Value normalization
# ---------------------------------------------------------------------------

_TRUE_WORDS = {"true", "já", "ja", "yes", "1"}
_FALSE_WORDS = {"false", "nei", "no", "0"}
_NULL_WORDS = {"null", "none", "nil", "-"}


def norm_value(raw: Any) -> str:
    """Normalize a TOS attribute value (or user query term) for comparison.

    Case-insensitive; the Icelandic boolean vocabulary (true/já/yes/1 and
    false/nei/no/0) canonicalizes to ``true`` / ``false`` so
    ``in_network_epos = true`` matches regardless of which variant a
    station's row carries. Whitespace is stripped.
    """
    s = str(raw).strip().lower()
    if s in _TRUE_WORDS:
        return "true"
    if s in _FALSE_WORDS:
        return "false"
    return s


def is_null_term(value: str) -> bool:
    """True when a predicate value means 'absent' (``null`` keyword)."""
    return value.strip().lower() in _NULL_WORDS


# ---------------------------------------------------------------------------
# Attribute predicates
# ---------------------------------------------------------------------------

#: Operator alternation — ``!=`` / ``!~`` must precede ``=`` / ``~`` so the
#: regex engine never bites the ``=`` half of ``!=``.
_EXPR_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*(!=|!~|=|~)\s*(.+?)\s*$")

#: Sugar flag → predicate mapping.
EPOS_CODE = "in_network_epos"


@dataclass(frozen=True)
class Predicate:
    """One station-attribute criterion: ``code op value``.

    ``op`` is one of ``=``, ``!=``, ``~``, ``!~``. The value ``null``
    (any casing) tests absence (``=``) or presence (``!=``) of the code.
    """

    code: str
    op: str
    value: str

    def describe(self) -> str:
        return f"{self.code} {self.op} {self.value}"


def parse_expression(expr: str) -> Predicate:
    """Parse ``'code OP value'`` into a :class:`Predicate`.

    Raises ``ValueError`` on a missing operator or an unparsable shape —
    the CLI turns that into a usage error (exit 2) with the syntax hint.
    """
    m = _EXPR_RE.match(expr)
    if not m:
        raise ValueError(
            f"cannot parse {expr!r} — expected 'code OP value' with OP one of "
            "= != ~ !~ (e.g. 'in_network_epos = true', 'marker ~ ve')"
        )
    code, op, value = m.groups()
    return Predicate(code=code.lower(), op=op, value=value)


def open_value(entity: dict, code: str) -> Optional[str]:
    """Value of the currently-open period for ``code``, or None.

    Mirrors :func:`tostools.devices.open_attribute` against the bulk
    search listing's attribute shape (``code`` / ``value`` / ``date_from``
    / ``date_to``). Closed periods are ignored — the search answers 'what
    does this station's Eigindi panel show today', matching the UI.
    """
    for attr in entity.get("attributes") or []:
        if attr.get("code") != code:
            continue
        if attr.get("date_to") is not None:
            continue
        v = attr.get("value")
        if v is not None:
            return str(v)
    return None


def predicate_matches(station: dict, pred: Predicate) -> bool:
    """Evaluate one :class:`Predicate` against a bulk-listing station dict."""
    current = open_value(station, pred.code)
    if pred.op in ("=", "!="):
        if is_null_term(pred.value):
            present = current is not None
            return present if pred.op == "!=" else not present
        if current is None:
            # Absent value: only an inequality can hold.
            return pred.op == "!="
        eq = norm_value(current) == norm_value(pred.value)
        return eq if pred.op == "=" else not eq
    # Substring ops.
    if current is None:
        return pred.op == "!~"
    hit = norm_value(pred.value) in norm_value(current)
    return hit if pred.op == "~" else not hit


def filter_by_predicates(
    stations: List[dict], predicates: List[Predicate]
) -> List[dict]:
    """Keep stations satisfying every predicate (AND)."""
    if not predicates:
        return list(stations)
    return [s for s in stations if all(predicate_matches(s, p) for p in predicates)]


# ---------------------------------------------------------------------------
# Device specs
# ---------------------------------------------------------------------------

#: Short alias → canonical TOS device subtype (superset of audit.py's
#: SUBTYPE_ALIASES — search also needs the telemetry hardware types that
#: appear in the TOS UI device panel: Beinir/router, SIM-kort/sim_card,
#: modem_gsm).
DEVICE_SUBTYPE_ALIASES: Dict[str, str] = {
    "receiver": "gnss_receiver",
    "gnss_receiver": "gnss_receiver",
    "antenna": "antenna",
    "radome": "radome",
    "monument": "monument",
    "modem": "modem_gsm",
    "modem_gsm": "modem_gsm",
    "sim": "sim_card",
    "sim_card": "sim_card",
    "router": "router",
}

#: Wildcard model terms — 'has any device of TYPE' rather than a model match.
_WILDCARDS = {"any", "*", ""}


@dataclass(frozen=True)
class DeviceSpec:
    """One device criterion: ``[TYPE:]MODEL`` with optional negation.

    ``subtype`` is the canonical TOS subtype or None (any type). ``model``
    is a normalized substring or None (any model). ``negate`` inverts the
    test (must NOT have such a device).
    """

    subtype: Optional[str] = None
    model: Optional[str] = None
    negate: bool = False

    def describe(self) -> str:
        lhs = self.subtype or "device"
        rhs = self.model or "any"
        op = "has-no" if self.negate else "has"
        return f"{op} {lhs}:{rhs}"


def parse_device_spec(raw: str, *, negate: bool = False) -> DeviceSpec:
    """Parse ``'[TYPE:]MODEL'`` into a :class:`DeviceSpec`.

    ``TYPE`` is a short alias or canonical subtype (receiver, antenna,
    radome, monument, modem, sim, router). ``MODEL`` is a case-insensitive
    substring; ``any`` / ``*`` (or empty) means any model — so
    ``router:any`` is 'has a router at all'. A bare ``teltonika`` (no
    colon) matches any device type by model.

    Raises ``ValueError`` on an unknown TYPE alias.
    """
    raw = raw.strip()
    subtype: Optional[str] = None
    model_part = raw
    if ":" in raw:
        type_part, model_part = raw.split(":", 1)
        type_part = type_part.strip().lower()
        if type_part and type_part not in _WILDCARDS:
            if type_part not in DEVICE_SUBTYPE_ALIASES:
                raise ValueError(
                    f"unknown device type {type_part!r} in {raw!r} — valid: "
                    + ", ".join(sorted(set(DEVICE_SUBTYPE_ALIASES)))
                )
            subtype = DEVICE_SUBTYPE_ALIASES[type_part]
        if not subtype:
            subtype = None
    model = model_part.strip().lower()
    if model in _WILDCARDS:
        model = None
    return DeviceSpec(subtype=subtype, model=model, negate=negate)


def device_spec_matches(device: dict, spec: DeviceSpec) -> bool:
    """Does one open-join device dict satisfy a (positive) spec?"""
    if spec.subtype and device.get("subtype") != spec.subtype:
        return False
    if spec.model:
        model = device.get("model")
        if model is None:
            return False
        if spec.model not in norm_value(model):
            return False
    return True


def devices_satisfy(
    devices: List[dict], must: List[DeviceSpec], must_not: List[DeviceSpec]
) -> bool:
    """True when the station's device list satisfies every spec.

    Positive specs are existential (at least one matching device each);
    negated specs are universal (no device may match).
    """
    for spec in must:
        if not any(device_spec_matches(d, spec) for d in devices):
            return False
    for spec in must_not:
        if any(device_spec_matches(d, spec) for d in devices):
            return False
    return True


# ---------------------------------------------------------------------------
# Attribute discovery (—-attribute-list / --allowed-values)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributeInventory:
    """Vocabulary discovery for one attribute code across a fleet listing.

    ``values`` are the distinct observed values with the number of stations
    carrying each (open or historical periods — the question answered is
    'what has TOS ever accepted here', which is what an operator needs
    before writing a predicate). ``constraint`` is TOS's own
    ``python_constraint`` regex from the attribute metadata.
    """

    code: str
    name_is: Optional[str] = None
    description_en: Optional[str] = None
    datatype: Optional[str] = None
    constraint: Optional[str] = None
    station_count: int = 0
    values: List[tuple] = field(default_factory=list)


def attribute_inventory(
    stations: List[dict], code: Optional[str] = None
) -> List[AttributeInventory]:
    """Aggregate distinct attribute codes / values over a fleet listing.

    ``code`` restricts the inventory to one attribute (single-element list,
    empty when the code is never observed). Station counts are distinct
    id_entities; per-value counts likewise count stations, not periods.
    """
    agg: Dict[str, Dict[str, Any]] = {}
    for st in stations:
        sid = st.get("id_entity")
        for a in st.get("attributes") or []:
            c = a.get("code")
            if not c or (code is not None and c != code):
                continue
            entry = agg.setdefault(c, {"stations": set(), "values": {}, "meta": a})
            entry["stations"].add(sid)
            v = a.get("value")
            if v is not None:
                entry["values"].setdefault(str(v), set()).add(sid)
    out: List[AttributeInventory] = []
    for c, e in agg.items():
        meta = e["meta"]
        values = sorted(
            ((v, len(ids)) for v, ids in e["values"].items()),
            key=lambda x: (-x[1], x[0]),
        )
        out.append(
            AttributeInventory(
                code=c,
                name_is=meta.get("name_is"),
                description_en=meta.get("description_en"),
                datatype=meta.get("attribute_datatype_code"),
                constraint=meta.get("python_constraint"),
                station_count=len(e["stations"]),
                values=values,
            )
        )
    out.sort(key=lambda i: (-i.station_count, i.code))
    return out


# ---------------------------------------------------------------------------
# Fleet fetch + device walk
# ---------------------------------------------------------------------------


def fetch_fleet(client: Any, domain: str = "geophysical") -> List[dict]:
    """Bulk-fetch every station in ``domain`` (one HTTP call)."""
    return client.list_stations(domain=domain) or []


def station_open_devices(client: Any, station_id: int) -> List[dict]:
    """Currently-joined devices of one station — the UI device panel.

    One history call for the station (children_connections) plus one per
    open child join (serial / model / subtype / status). Devices are the
    rows ``tos device list --station`` prints.
    """
    hist = client.get_entity_history(station_id) or {}
    devices: List[dict] = []
    for conn in hist.get("children_connections") or []:
        if conn.get("time_to") is not None:
            continue  # closed join — device no longer at the station
        child_id = conn.get("id_entity_child")
        if child_id is None:
            continue
        try:
            child_id = int(child_id)
        except (TypeError, ValueError):
            continue
        child = client.get_entity_history(child_id) or {}
        devices.append(
            {
                "id_entity": child_id,
                "serial": open_value(child, "serial_number") or "?",
                "model": open_value(child, "model"),
                "subtype": child.get("code_entity_subtype") or "?",
                "status": open_value(child, "status") or "—",
                "since": conn.get("time_from"),
            }
        )
    return devices


def walk_devices(
    client: Any,
    station_ids: List[int],
    *,
    max_workers: int = 8,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Dict[int, List[dict]]:
    """Open-join devices for many stations, walked on a thread pool.

    A failed station (TOS error) yields an empty list + a warning, never
    an abort — a flaky single station must not sink the fleet search.
    Returns ``{id_entity: [device, ...]}``.
    """
    out: Dict[int, List[dict]] = {}
    ids = list(station_ids)
    if not ids:
        return out
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(station_open_devices, client, sid): sid for sid in ids}
        for done, fut in enumerate(as_completed(futures), 1):
            sid = futures[fut]
            try:
                out[sid] = fut.result()
            except Exception as exc:  # noqa: BLE001 — per-station isolation
                logger.warning("device walk failed for id_entity=%s: %s", sid, exc)
                out[sid] = []
            if progress is not None:
                progress(done, len(ids))
    return out


def stderr_progress(
    no_progress: bool, json_mode: bool
) -> Optional[Callable[[int, int], None]]:
    """Build a stderr progress callback, or None when suppressed.

    Suppressed when ``--no-progress``, ``--json`` (stdout purity), or when
    stderr is not a TTY (CI / pipe — same policy as ``tos device find``).
    """
    if no_progress or json_mode or not sys.stderr.isatty():
        return None

    def emit(done: int, total: int) -> None:
        end = "\n" if done == total else ""
        sys.stderr.write(f"\r  devices: {done}/{total} stations{end}")
        sys.stderr.flush()

    return emit


# ---------------------------------------------------------------------------
# Combined pipeline
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Everything the renderer needs, criteria summary included."""

    stations: List[dict] = field(default_factory=list)
    predicates: List[Predicate] = field(default_factory=list)
    show_codes: List[str] = field(default_factory=list)
    device_must: List[DeviceSpec] = field(default_factory=list)
    device_must_not: List[DeviceSpec] = field(default_factory=list)
    devices_by_id: Dict[int, List[dict]] = field(default_factory=dict)

    @property
    def device_filters_active(self) -> bool:
        return bool(self.device_must or self.device_must_not)

    @property
    def attribute_codes(self) -> List[str]:
        """Codes to render as columns: predicate codes + --show codes."""
        codes: List[str] = []
        for pred in self.predicates:
            if pred.code not in codes:
                codes.append(pred.code)
        for code in self.show_codes:
            if code not in codes:
                codes.append(code)
        return codes


def search_stations(
    client: Any,
    predicates: List[Predicate],
    *,
    device_must: Optional[List[DeviceSpec]] = None,
    device_must_not: Optional[List[DeviceSpec]] = None,
    show_codes: Optional[List[str]] = None,
    domain: str = "geophysical",
    progress: Optional[Callable[[int, int], None]] = None,
    max_workers: int = 8,
) -> SearchResult:
    """Run the full pipeline: bulk fetch → attribute filter → device walk.

    The device walk (1 + N HTTP calls per station) only touches stations
    that survived the attribute stage, so ``tos search --epos --receiver
    polarx5`` costs one bulk call, ~N_station-history calls, then per-open-
    child calls — not 200 × full device history up front.
    """
    device_must = device_must or []
    device_must_not = device_must_not or []
    fleet = fetch_fleet(client, domain=domain)
    survivors = filter_by_predicates(fleet, predicates)

    devices_by_id: Dict[int, List[dict]] = {}
    if device_must or device_must_not:
        devices_by_id = walk_devices(
            client,
            [s.get("id_entity") for s in survivors if s.get("id_entity")],
            max_workers=max_workers,
            progress=progress,
        )
        survivors = [
            s
            for s in survivors
            if devices_satisfy(
                devices_by_id.get(s.get("id_entity"), []), device_must, device_must_not
            )
        ]

    # Sort by marker (fallback name), then apply limit upstream in the CLI.
    def _sort_key(s: dict) -> str:
        return norm_value(open_value(s, "marker") or open_value(s, "name") or "")

    survivors.sort(key=_sort_key)

    return SearchResult(
        stations=survivors,
        predicates=list(predicates),
        show_codes=[c.lower() for c in (show_codes or [])],
        device_must=device_must,
        device_must_not=device_must_not,
        devices_by_id=devices_by_id,
    )
