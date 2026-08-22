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
# Text matching — substring (default), glob, regex
# ---------------------------------------------------------------------------

#: Opt-in prefix selecting regex semantics for a ``~`` / ``!~`` term.
REGEX_PREFIX = "re:"

#: Characters that make a ``~`` term a glob rather than a plain substring.
_GLOB_META = ("*", "?", "[")


def has_glob(term: str) -> bool:
    """True when ``term`` carries glob metacharacters."""
    return any(ch in term for ch in _GLOB_META)


def text_matches(current: Any, term: str) -> bool:
    """Does ``current`` satisfy a ``~`` term?

    Three styles, and which one applies is decided by the term itself so
    that nothing is ever reinterpreted behind the operator's back:

    1. ``re:PATTERN`` — regex, unanchored (``.search``). Opt-in only: a
       term is NEVER treated as a regex unless it says so, because
       ``name ~ a.b`` must keep meaning a literal ``a.b``.
    2. Contains ``*`` / ``?`` / ``[`` — glob, **fully anchored**
       (``fnmatch``): ``marker ~ HVE*`` is 'starts with HVE', not
       'contains HVE*'. Wrap in stars for substring: ``~ *vík*``.
    3. Anything else — plain substring, exactly as before this feature.

    Both sides go through :func:`norm_value` first, so the Icelandic
    boolean folding (``já``/``nei``) and case-insensitivity that plain
    substring matching has always had apply to patterns too.
    """
    if current is None:
        return False
    hay = norm_value(current)

    if term.startswith(REGEX_PREFIX):
        raw = term[len(REGEX_PREFIX) :]
        if not raw:
            raise ValueError(
                f"empty regex after {REGEX_PREFIX!r} — e.g. 'name ~ re:veður|vega'"
            )
        try:
            rx = re.compile(raw, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"bad regex {raw!r}: {exc}") from exc
        return rx.search(hay) is not None

    if has_glob(term):
        import fnmatch

        return fnmatch.fnmatch(hay, norm_value(term))

    return norm_value(term) in hay


# ---------------------------------------------------------------------------
# Selectors — 'code' (station) or 'namespace.code' (joined device)
# ---------------------------------------------------------------------------

#: Namespace meaning 'a device of any subtype'.
ANY_DEVICE = "*"


class UnsupportedSelector(ValueError):
    """A selector is well-formed but cannot be answered on this code path.

    Subclasses ``ValueError`` so the CLI's existing parse-error path turns
    it into a usage error (exit 2) with the message attached.
    """


def parse_selector(raw: str) -> tuple:
    """Split ``'code'`` or ``'namespace.code'`` into ``(namespace, code)``.

    A bare code addresses a **station** attribute and returns namespace
    ``None`` — unchanged from before this feature. A dotted selector
    addresses an attribute of a currently-joined **device**::

        receiver.firmware_version   the station's GNSS receiver
        antenna.serial_number
        *.model                     a device of any subtype

    The namespace accepts the same aliases as ``--device TYPE:MODEL``, so
    ``receiver`` and ``gnss_receiver`` are interchangeable. Raises
    ``ValueError`` on an unknown namespace, listing the valid ones.
    """
    raw = raw.strip()
    if "." not in raw:
        return None, raw.lower()

    ns, _, code = raw.partition(".")
    ns = ns.strip().lower()
    code = code.strip().lower()
    if not code:
        raise ValueError(
            f"selector {raw!r} has no attribute after the dot — "
            "e.g. 'receiver.firmware_version'"
        )
    if ns == ANY_DEVICE:
        return ANY_DEVICE, code
    # DEVICE_SUBTYPE_ALIASES is defined further down (device-spec section);
    # module globals resolve at call time, so the forward reference is fine.
    if ns not in DEVICE_SUBTYPE_ALIASES:
        raise ValueError(
            f"unknown device namespace {ns!r} in {raw!r} — valid: "
            + ", ".join(sorted(set(DEVICE_SUBTYPE_ALIASES)) + [ANY_DEVICE])
        )
    return DEVICE_SUBTYPE_ALIASES[ns], code


def require_station_selector(namespace: Optional[str], raw: str) -> None:
    """Guard the station-only code paths against a device selector.

    Device selectors ARE supported (see
    :func:`predicate_matches_devices`), but they can only be answered from
    the per-station device walk. The bulk station listing carries no
    devices, so anything evaluating against it must refuse rather than
    quietly report False.
    """
    if namespace is not None:
        raise UnsupportedSelector(
            f"device selector {raw!r} cannot be resolved from the bulk "
            "station listing — it needs the per-station device walk. This is "
            "an internal guard; report it as a bug if you hit it from the CLI."
        )


# ---------------------------------------------------------------------------
# Attribute predicates
# ---------------------------------------------------------------------------

#: Operator alternation — ``!=`` / ``!~`` must precede ``=`` / ``~`` so the
#: regex engine never bites the ``=`` half of ``!=``.
#: The code group accepts ``.`` and ``*`` so a selector namespace
#: (``receiver.firmware_version``, ``*.model``) parses here rather than
#: failing as an unparsable expression.
_EXPR_RE = re.compile(r"^\s*([A-Za-z0-9_.*]+)\s*(!=|!~|=|~)\s*(.+?)\s*$")

#: Sugar flag → predicate mapping.
EPOS_CODE = "in_network_epos"


@dataclass(frozen=True)
class Predicate:
    """One station-attribute criterion: ``code op value``.

    ``op`` is one of ``=``, ``!=``, ``~``, ``!~``, plus the list forms
    ``in`` / ``not in`` (``code = [a, b]``). The value ``null`` (any
    casing) tests absence (``=``) or presence (``!=``) of the code; the
    value ``all`` (any casing) matches everything (``=``) or nothing
    (``!=``) — used by ``subtype = all`` to lift the default GPS scope.
    """

    code: str
    op: str
    value: str = ""
    values: tuple = ()
    namespace: Optional[str] = None

    @property
    def selector(self) -> str:
        """Human-facing selector: ``code`` or ``namespace.code``."""
        return f"{self.namespace}.{self.code}" if self.namespace else self.code

    def describe(self) -> str:
        if self.op in ("in", "not in"):
            opstr = "in" if self.op == "in" else "not in"
            return f"{self.selector} {opstr} [{', '.join(self.values)}]"
        return f"{self.selector} {self.op} {self.value}"


#: The operational IMO GNSS fleet definition — what ``--active-gps`` expands
#: to: GPS subtype, not ended (no open Lokadagsetning), on bedrock rather
#: than a moving glacier (geological != ice, absent geology passes), and
#: recorded as a continuous station (Samfella = continuous — strict, so
#: unrecorded continuity does NOT pass; fill the attribute instead).
ACTIVE_GPS_PREDICATES = (
    Predicate("subtype", "=", "GPS stöð"),
    Predicate("date_end", "=", "null"),
    Predicate("geological_characteristic", "!=", "ice"),
    Predicate("continuity", "=", "continuous"),
)


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
    raw_code, op, value = m.groups()
    namespace, code = parse_selector(raw_code)
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        items = [v.strip() for v in stripped[1:-1].split(",") if v.strip()]
        if not items:
            raise ValueError(
                f"empty list in {expr!r} — e.g. 'subtype = [GPS stöð, SIL stöð]'"
            )
        if op == "=":
            return Predicate(
                code=code, op="in", values=tuple(items), namespace=namespace
            )
        if op == "!=":
            return Predicate(
                code=code, op="not in", values=tuple(items), namespace=namespace
            )
        raise ValueError(
            f"list value only supports '=' / '!=' (got {op!r} in {expr!r})"
        )
    return Predicate(code=code, op=op, value=value, namespace=namespace)


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
    """Evaluate one :class:`Predicate` against a bulk-listing station dict.

    Station-attribute predicates only — a device selector cannot be
    answered from the bulk listing (it carries no devices) and is rejected
    here as a backstop, since the CLI already refuses it at parse time.
    """
    require_station_selector(pred.namespace, pred.selector)
    current = open_value(station, pred.code)
    if pred.op == "in":
        if current is None:
            return False
        wanted = {norm_value(v) for v in pred.values}
        return norm_value(current) in wanted
    if pred.op == "not in":
        if current is None:
            return True  # absent is trivially "not in" the list
        wanted = {norm_value(v) for v in pred.values}
        return norm_value(current) not in wanted
    if pred.op in ("=", "!="):
        if norm_value(pred.value) == "all":
            return pred.op == "="  # '= all' → True; '!= all' → False
        if is_null_term(pred.value):
            present = current is not None
            return present if pred.op == "!=" else not present
        if current is None:
            # Absent value: only an inequality can hold.
            return pred.op == "!="
        eq = norm_value(current) == norm_value(pred.value)
        return eq if pred.op == "=" else not eq
    # Text ops — substring, glob (``*``/``?``), or ``re:`` regex.
    if current is None:
        return pred.op == "!~"
    hit = text_matches(current, pred.value)
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


def device_in_namespace(device: dict, namespace: str) -> bool:
    """Is this joined device addressed by ``namespace``?

    ``*`` (:data:`ANY_DEVICE`) matches every subtype; anything else is an
    exact canonical-subtype match.
    """
    if namespace == ANY_DEVICE:
        return True
    return device.get("subtype") == namespace


def device_values(devices: List[dict], namespace: str, code: str) -> List[Any]:
    """Open values of ``code`` across every device in ``namespace``.

    One entry per matching device, ``None`` where that device has no open
    period for the code. An empty list means the station has no device of
    that subtype at all — which is a different thing from having one whose
    attribute is unset, and the two are deliberately NOT collapsed: a
    station with two receivers contributes two entries, so nothing silently
    reports one receiver's firmware as though it were the station's.
    """
    return [open_value(d, code) for d in devices if device_in_namespace(d, namespace)]


def predicate_matches_devices(devices: List[dict], pred: Predicate) -> bool:
    """Evaluate a device-selector predicate against a station's devices.

    Aggregation is **existential**: the station matches when *any* device
    in the namespace satisfies the predicate. So
    ``receiver.firmware_version != 5.7.0`` means 'has a receiver that is
    not on 5.7.0', which on a two-receiver station is a weaker claim than
    'no receiver is on 5.7.0' — stated in ``--help`` rather than made
    configurable.

    Absence mirrors the station-attribute rules: with no value present,
    only a negative operator can hold, and ``= null`` / ``!= null`` test
    for the attribute's presence anywhere in the namespace.
    """
    values = device_values(devices, pred.namespace or ANY_DEVICE, pred.code)
    present = [v for v in values if v is not None]

    if pred.op in ("=", "!=") and norm_value(pred.value) == "all":
        return pred.op == "="
    if pred.op in ("=", "!=") and is_null_term(pred.value):
        return bool(present) if pred.op == "!=" else not present

    if not present:
        # Nothing to match: only a negation can hold, exactly as for an
        # absent station attribute.
        return pred.op in ("!=", "!~", "not in")

    if pred.op == "in":
        wanted = {norm_value(v) for v in pred.values}
        return any(norm_value(v) in wanted for v in present)
    if pred.op == "not in":
        wanted = {norm_value(v) for v in pred.values}
        return any(norm_value(v) not in wanted for v in present)
    if pred.op == "=":
        return any(norm_value(v) == norm_value(pred.value) for v in present)
    if pred.op == "!=":
        return any(norm_value(v) != norm_value(pred.value) for v in present)
    if pred.op == "~":
        return any(text_matches(v, pred.value) for v in present)
    if pred.op == "!~":
        return any(not text_matches(v, pred.value) for v in present)
    return False


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
                # Raw periods, so an arbitrary device selector
                # (receiver.firmware_version) can be resolved without a
                # second fetch. Keyed "attributes" so open_value() works on
                # this dict directly. The CLI renders an explicit summary
                # rather than dumping the dict, so this never reaches JSON.
                "attributes": child.get("attributes") or [],
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
        """STATION columns: bare predicate codes + bare --show selectors.

        Dotted selectors are device columns and are excluded here — see
        :attr:`device_columns`.
        """
        codes: List[str] = []
        for pred in self.predicates:
            if pred.namespace is None and pred.code not in codes:
                codes.append(pred.code)
        for raw in self.show_codes:
            if "." in raw:
                continue
            if raw not in codes:
                codes.append(raw)
        return codes

    @property
    def device_columns(self) -> List[tuple]:
        """DEVICE columns as ``(namespace, code)``: predicates + --show."""
        cols: List[tuple] = []
        for pred in self.predicates:
            if pred.namespace is not None:
                pair = (pred.namespace, pred.code)
                if pair not in cols:
                    cols.append(pair)
        for raw in self.show_codes:
            if "." not in raw:
                continue
            pair = parse_selector(raw)
            if pair not in cols:
                cols.append(pair)
        return cols

    @property
    def device_selectors_active(self) -> bool:
        return bool(self.device_columns)

    def device_column_value(self, station: dict, namespace: str, code: str) -> str:
        """Rendered cell for one device column on one station.

        Every device in the namespace contributes an entry, joined by
        ``, `` — so a station with two receivers shows both firmware
        values rather than whichever the walk happened to return first.
        """
        devices = self.devices_by_id.get(station.get("id_entity"), [])
        values = device_values(devices, namespace, code)
        rendered = [str(v) if v is not None else "—" for v in values]
        return ", ".join(rendered) if rendered else "—"


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
    raw_show = [c.lower() for c in (show_codes or [])]

    # Station predicates prune the fleet BEFORE any device walk; device
    # predicates can only be evaluated after it.
    station_preds = [p for p in predicates if p.namespace is None]
    device_preds = [p for p in predicates if p.namespace is not None]

    fleet = fetch_fleet(client, domain=domain)
    survivors = filter_by_predicates(fleet, station_preds)

    # A device selector needs the walk even with no --device/--receiver
    # filter — projecting receiver.firmware_version is reason enough.
    show_needs_devices = any("." in c for c in raw_show)
    need_devices = bool(
        device_must or device_must_not or device_preds or show_needs_devices
    )

    devices_by_id: Dict[int, List[dict]] = {}
    if need_devices:
        devices_by_id = walk_devices(
            client,
            [s.get("id_entity") for s in survivors if s.get("id_entity")],
            max_workers=max_workers,
            progress=progress,
        )
        if device_must or device_must_not:
            survivors = [
                s
                for s in survivors
                if devices_satisfy(
                    devices_by_id.get(s.get("id_entity"), []),
                    device_must,
                    device_must_not,
                )
            ]
        if device_preds:
            survivors = [
                s
                for s in survivors
                if all(
                    predicate_matches_devices(
                        devices_by_id.get(s.get("id_entity"), []), p
                    )
                    for p in device_preds
                )
            ]

    # Sort by marker (fallback name), then apply limit upstream in the CLI.
    def _sort_key(s: dict) -> str:
        return norm_value(open_value(s, "marker") or open_value(s, "name") or "")

    survivors.sort(key=_sort_key)

    return SearchResult(
        stations=survivors,
        predicates=list(predicates),
        show_codes=raw_show,
        device_must=device_must,
        device_must_not=device_must_not,
        devices_by_id=devices_by_id,
    )
