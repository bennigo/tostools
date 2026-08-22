"""On-disk cache + snapshot recording for TOS read calls.

``tos search`` is used iteratively — run it, read the table, refine the
selector, run again. Station attributes come from one bulk GET, but any
device selector forces a per-station history walk (``1 + N_children``
calls), so an unrefined loop pays that cost every time. This module wraps
a TOS client so the two read calls the search engine makes —
``list_stations`` and ``get_entity_history`` — are served from disk when
they are fresh enough.

**Staleness is always reported, never inferred.** This output drives live
TOS writes; a silently stale row is how you PATCH the wrong device. Every
run that served anything from cache prints the age of its oldest hit, and
``--from-snapshot`` prints when the snapshot was taken.

Two mechanisms, deliberately different granularities:

- **cache** — automatic, per-entity, TTL'd, invisible until it matters.
- **snapshot** — an explicit named file recording everything a run
  fetched, replayed with no network at all. A dated artifact for
  reproducibility and audit trails, where the staleness is visible in the
  filename you chose.

The cache lives under ``$XDG_CACHE_HOME/tostools`` (not the
``~/.local/share/tostools`` tree, which holds synced metadata — that is
data, this is disposable).

Thread-safe: ``walk_devices`` calls ``get_entity_history`` from a
thread pool, so the counters, the recording buffer and the on-disk writes
all have to tolerate concurrency.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.logging import get_logger

logger = get_logger(__name__, logging.WARNING)

#: Default freshness window. Long enough for an iterative session, short
#: enough that a value cannot quietly age into a working day.
DEFAULT_TTL_SECONDS = 900

#: Bumped if the on-disk shape ever changes incompatibly.
SNAPSHOT_VERSION = 1


class SnapshotMiss(RuntimeError):
    """A replayed run asked for something the snapshot does not contain."""


def cache_root(server: Optional[str] = None) -> Path:
    """Base directory for the TOS read cache (XDG-compliant).

    Partitioned **per server**: entity ids are only unique within one TOS
    instance, so a shared directory would serve production rows to a run
    pointed at a test server. Honours ``$XDG_CACHE_HOME``, which is also
    how the test suite keeps off a developer's real cache.
    """
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    root = Path(base) / "tostools" / "tos-read"
    return root / _server_slug(server) if server else root


def _server_slug(server: str) -> str:
    """Filesystem-safe directory name for a TOS base URL or host."""
    keep = [c if (c.isalnum() or c in "-.") else "_" for c in str(server)]
    slug = "".join(keep).strip("_.") or "default"
    return slug[:80]


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON so a concurrent reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def humanize_age(seconds: float) -> str:
    """Compact age string: ``42s`` / ``6m`` / ``3h`` / ``2d``."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


class CachingClient:
    """Wrap a TOS client with an on-disk read cache + snapshot recording.

    Only the two read calls ``tos search`` makes are intercepted. Anything
    else falls through via ``__getattr__``, so this stays a transparent
    stand-in for the real client.

    The recording buffer is populated on hits *and* misses, so
    ``--snapshot`` captures a complete run whether or not the cache was
    warm, and works with ``--no-cache``.
    """

    def __init__(
        self,
        inner: Any,
        *,
        ttl: int = DEFAULT_TTL_SECONDS,
        enabled: bool = True,
        refresh: bool = False,
        cache_dir: Optional[Path] = None,
        server: Optional[str] = None,
    ):
        self._inner = inner
        self._ttl = max(0, int(ttl))
        self._enabled = enabled
        self._refresh = refresh
        self._dir = Path(cache_dir) if cache_dir else cache_root(server)
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self._oldest_hit: Optional[float] = None
        self._recorded_stations: Dict[str, Any] = {}
        self._recorded_entities: Dict[str, Any] = {}

    # -- plumbing ---------------------------------------------------------

    def __getattr__(self, name):  # pragma: no cover - passthrough
        return getattr(self._inner, name)

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def _read(self, key: str) -> Optional[Any]:
        """Fresh cached payload for ``key``, or None."""
        if not self._enabled or self._refresh:
            return None
        path = self._path(key)
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return None
        if age > self._ttl:
            return None
        try:
            with path.open(encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("cache read failed for %s: %s", key, exc)
            return None
        with self._lock:
            self.hits += 1
            if self._oldest_hit is None or age > self._oldest_hit:
                self._oldest_hit = age
        return payload

    def _write(self, key: str, payload: Any) -> None:
        if not self._enabled:
            return
        try:
            _atomic_write_json(self._path(key), payload)
        except OSError as exc:
            # A cache that cannot be written must never break a search.
            logger.debug("cache write failed for %s: %s", key, exc)

    # -- intercepted reads ------------------------------------------------

    def list_stations(self, domain: str = "geophysical") -> List[dict]:
        key = f"stations-{domain}"
        payload = self._read(key)
        if payload is None:
            payload = self._inner.list_stations(domain=domain)
            with self._lock:
                self.misses += 1
            self._write(key, payload)
        with self._lock:
            self._recorded_stations[domain] = payload
        return payload

    def get_entity_history(self, id_entity: int) -> Optional[dict]:
        key = f"entity-{int(id_entity)}"
        payload = self._read(key)
        if payload is None:
            payload = self._inner.get_entity_history(id_entity)
            with self._lock:
                self.misses += 1
            if payload is not None:
                self._write(key, payload)
        with self._lock:
            self._recorded_entities[str(int(id_entity))] = payload
        return payload

    # -- reporting --------------------------------------------------------

    def cache_note(self) -> Optional[str]:
        """One-line staleness report, or None when nothing was cached.

        Printed on every run that served a cache hit — the condition this
        module exists under. Names ``--refresh`` because a reader who
        distrusts the age needs the remedy in the same breath.
        """
        with self._lock:
            hits, misses, oldest = self.hits, self.misses, self._oldest_hit
        if not hits:
            return None
        age = humanize_age(oldest) if oldest is not None else "?"
        return (
            f"cache: {hits} hit / {misses} fetched — oldest entry {age} old "
            f"(--refresh to re-fetch, --no-cache to bypass)"
        )

    # -- snapshot ---------------------------------------------------------

    def snapshot_payload(self, **meta: Any) -> dict:
        """Everything this run read, as a replayable document."""
        with self._lock:
            return {
                "tostools_snapshot": SNAPSHOT_VERSION,
                "created": datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "meta": meta,
                "stations": dict(self._recorded_stations),
                "entities": dict(self._recorded_entities),
            }

    def write_snapshot(self, path: Path, **meta: Any) -> Path:
        path = Path(path).expanduser()
        _atomic_write_json(path, self.snapshot_payload(**meta))
        return path


class SnapshotClient:
    """Replay a snapshot file. Never touches the network.

    A lookup the snapshot does not contain raises :class:`SnapshotMiss`
    rather than returning None: a missing entity would otherwise read as
    'this station has no devices', which is a wrong answer dressed as a
    real one.
    """

    def __init__(self, payload: dict, *, source: Optional[str] = None):
        version = payload.get("tostools_snapshot")
        if version != SNAPSHOT_VERSION:
            raise ValueError(
                f"unsupported snapshot version {version!r} "
                f"(this build reads version {SNAPSHOT_VERSION}) — re-take it"
            )
        self._stations = payload.get("stations") or {}
        self._entities = payload.get("entities") or {}
        self.created = payload.get("created")
        self.meta = payload.get("meta") or {}
        self.source = source

    @classmethod
    def load(cls, path) -> "SnapshotClient":
        path = Path(path).expanduser()
        with path.open(encoding="utf-8") as fh:
            return cls(json.load(fh), source=str(path))

    def list_stations(self, domain: str = "geophysical") -> List[dict]:
        if domain not in self._stations:
            raise SnapshotMiss(
                f"snapshot has no station listing for domain {domain!r} "
                f"(recorded: {', '.join(sorted(self._stations)) or 'none'})"
            )
        return self._stations[domain]

    def get_entity_history(self, id_entity: int) -> Optional[dict]:
        key = str(int(id_entity))
        if key not in self._entities:
            raise SnapshotMiss(
                f"snapshot has no history for id_entity={key} — it was taken "
                "with a narrower query than this one. Re-take it with the "
                "wider query, or drop --from-snapshot."
            )
        return self._entities[key]

    def snapshot_note(self) -> str:
        """Provenance line — always printed, staleness is the whole point."""
        where = f" {self.source}" if self.source else ""
        return (
            f"snapshot{where}: recorded {self.created or 'unknown'} "
            f"({len(self._entities)} entities) — NO live TOS read"
        )
