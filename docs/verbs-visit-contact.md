# `tos visit` and `tos contact` — verb reference

Routed out of `CLAUDE.md` 2026-08-23 to keep that file within the 150-line
subdirectory budget (see `gpslibrary/CLAUDE.md` → Maintenance). Content is
unchanged from the version that lived there.

### `tos visit` — vitjun (visit / maintenance) inspection

Vitjanir are entity-attached temporal records (`id_maintenance`
namespace, distinct from `id_entity` / `id_contact`). The schema is
generic on `id_entity`: stations and devices can both carry vitjanir.
In current GPS data every vitjun is station-attached (device-attached
vitjanir today are exclusively on meteorological sensors); Phase C of
the vitjanir expansion will start writing device-attached vitjanir for
the GPS lifecycle tracker (firmware bumps, sent-for-repair, etc.).

  * `tos visit list --station S` — vitjanir for a station, most-recent first
  * `tos visit list --device <id>` — vitjanir for a single device
  * `tos visit list --entity <id>` — escape hatch (any entity by id)
  * `tos visit show <id_maintenance>` — one vitjun, full detail
    including `maintenance_attribute_values` rows (`work` / `comment` /
    `remaining` / per-reason booleans + each row's
    `id_maintenance_attribute_value` for the writer's update path)

Standard filter set (read-only): `--type {on_site,remote}`,
`--reason CODE` (repeatable; `change` / `repairs` / `inspection` /
`improvements` / `other`), `--since DATE`, `--participants SUBSTR`,
`--open` / `--completed`. The `--reason` filter translates English
codes to the Icelandic display strings TOS emits on the list endpoint
(see `MAINTENANCE_REASON_DISPLAY` in `src/tostools/tos.py`).

`tos station show` and `tos device show --id <id>` surface a "Recent
vitjanir" section by default — every open visit + the 3 most-recent
closed. Station show aggregates from the station + currently-joined
devices with a `source` column for attribution (forward-compatible
with Phase C). `--no-visits` suppresses the section (and skips the
HTTP); `--all` on station show extends to full visit history.

**`tos visit add`** (Phase B — record-forward write verb):

  * `tos visit add --station S --start DATE [--end DATE] [--type {on_site,remote}] [--participants EMAIL ...] [--reason CODE ...] [--work TEXT] [--comment TEXT] [--remaining TEXT] [--no-completed] [--no-dry-run]`
  * Dry-run by default — payloads are logged but no writes are sent (matches `tos device add`). `--no-dry-run` commits (requires TOS credentials).
  * Target: `--station S` (resolved via marker), `--device <id>` (direct id_entity, semantically a device — the Phase C lifecycle tracker's main path), or `--entity <id>` (escape hatch).
  * Validation: `--reason` choices restricted to `MAINTENANCE_REASON_CODES`; argparse rejects bad codes before the writer. The writer additionally validates `maintenance_type` and date format; on `ValueError` the CLI exits 1 with the writer's message.
  * `--participants` is repeatable (joined comma-separated for TOS). `--reason` is repeatable (multiple reasons true on one vitjun).
  * `--no-completed` marks the visit open (long-running repair / ongoing investigation).
  * Implementation wraps `TOSWriter.add_maintenance_visit` (the existing 3-call POST + GET + PUT flow that handles auto-seeded `maintenance_attribute_value` rows).

**`tos visit search`** (fleet-wide free-text, 2026-08-24):

  * `tos visit search --work TEXT [--type {on_site,remote}] [--epos] [--missing] [--markers-only] [--json] [EXPRESSION ...]`
  * Searches EVERY station's vitjanir by free text on the work field — the fleet-level complement to per-station `list`. `--work` and `--type` are optional and AND-ed.
  * `--missing` inverts to stations WITHOUT a match. Positional EXPRESSIONs + the shared sugar flags (`--epos`/`--active-gps`/`--continuous`/…) scope the station set first.
  * **For a station-level YES/NO cross-check, the `visit.*` selectors in `tos search` are the primary form** (`tos search --epos 'visit.all !~ "TOS reviewed"'`); `visit search` lists the matching VISIT rows (id + date) for drill-down.

**`add-visit` ACTION verb** (Phase C — device lifecycle tracker, v1):

Triage-file integration for the lifecycle workflow. Operators chain
vitjun creation next to `move` / `decommission` / `add-attribute`
ACTIONs in the same file so a single `tos audit apply` commits
metadata changes + the audit trail of physical interventions
together.

Syntax: `ACTION <id_entity> add-visit <reasons_csv> <date> <work_text> [open|closed]`

  * `<reasons_csv>`: one or more reason codes, comma-separated (no
    spaces — shlex keeps the token intact, dispatcher splits
    internally). Each code validated against
    `MAINTENANCE_REASON_CODES` BEFORE the writer call.
  * `<date>`: `YYYY-MM-DD` or `now` / `start` tokens (same resolver
    as `add-attribute`).
  * `<work_text>`: free-text description, quote with `'` or `"` to
    contain spaces (shlex).
  * 4th positional: `open` or `closed`, defaults `closed`. Use
    `open` for the start of a long-running repair cycle.

Defaults (cannot be overridden from triage v1): `maintenance_type=on_site`,
`participants=""`, `comment=None`, `remaining=None`. Operators needing
those fields use `tos visit add --no-dry-run` directly. Phase C.5
follow-ups: participants auto-fill from `[tos] username`,
`comment`/`remaining` slots, `--with-visit` modifier on other verbs,
auto-template from operation diff.

Worked lifecycle-tracker example — sent for repair → fixed →
back from repair:

```
# device 4830 (SAVI POLARX2) sent to vendor 2026-05-30 for cable damage
ACTION 4830 move 4 2026-05-30                           # → warehouse B9
ACTION 4830 add-visit repairs 2026-05-30 "sent for repair: cable damage" open

# vendor sent device back 2026-06-15
ACTION 4830 add-visit repairs 2026-06-15 "vendor diagnosed; cable replaced"

# re-deployed at HEDI 2026-06-20 with firmware bump
ACTION 4830 move 4316 2026-06-20                        # → HEDI station
ACTION 4830 patch-attribute-value firmware_version 2026-06-20 "3.01"
ACTION 4830 add-visit change,repairs 2026-06-20 "back from vendor; firmware bumped to 3.01"
```

Three vitjanir document the three operator-visible states; the move +
patch ACTIONs reflect the underlying TOS state changes.

**`tos audit visit-coverage`** (Phase D — invariant audit):

Cross-references a station's join history against its vitjun history
and flags equipment-change events with no vitjun within ±N days.
Closes the loop on the lifecycle-tracker workflow — surfaces drift
when operators forget to leave `add-visit` entries on real device
deployments.

  * `tos audit visit-coverage <STN>` — standalone audit
  * `tos audit visit-coverage <STN> --since 2020-01-01` — widen historical scope
  * `tos audit visit-coverage <STN> --coverage-window-days 14` — widen tolerance
  * `tos audit visit-coverage <STN> --triage path.txt` — emit `add-visit` ACTIONs

v1 scope is intentionally narrow:
  * **Opens only** — not closes or attribute writes
  * **Station-attached vitjanir only** — empirically zero GPS-device vitjanir today; device-side check will land via `--include-device-visits` if usage warrants
  * **Last 2 years by default** — older events are silently skipped; pre-vitjun-era stations would otherwise overwhelm the SUPPRESS workflow
  * **Skips the 2014-10-17 cleanup-artifact pattern** — those aren't real install dates

Integrates as opt-in third audit in the verify oracle / fleet status:

  * `tos station verify HEDI --with-coverage` adds the coverage check
  * `tos fleet status --with-coverage` runs it across all 173 stations
  * `tos fleet triage --with-coverage` includes coverage section in per-station triage files

Off by default to avoid the first-run noise problem: until operators have used `add-visit` enough to establish a baseline, every station looks broken. SUPPRESS file at `data/audit_suppressions/visit_coverage.txt` (key shape: `SUPPRESS <device_id> <event_date>`) lets operators silence pre-vitjun-era findings as they triage.

Triage emitter generates one commented `#ACTION <device_id> add-visit change <event_date> "<FILL_WORK>"` per violation + a SUPPRESS hint per line. Operator replaces `<FILL_WORK>` with what actually happened, uncomments the line, runs `tos audit apply`.

### `tos contact` — contact↔station relationship writes

A contact (`id_contact`, e.g. 1256 = Veðurstofa) is mapped to a
station/device by a relationship row in its own namespace
(`id_contact_entity_relationship`). The raw admin row is
`{id, id_contact, id_entity, role, time_from, time_to}` — structurally
identical to an entity_connection. Endpoints (discovered 2026-05-31 by
read-only probing; see `docs/architecture/contact-write-api.md`):
`GET/PUT/DELETE /admin_contact_entity_relationship_row/{id}`,
`POST /contact_joins` (create).

Read verbs (`tos contact show / list`) are unchanged. **Write verbs**
(dry-run by default, `--no-dry-run` commits — same as `tos visit add`):

  * `tos contact patch-relationship <id_rel> --time-from DATE [--time-to DATE] [--role R]`
    — the primary use: backdate a `time_from` that is a TOS-migration
    artifact (the relationship row was created when the contact was
    loaded into the new TOS, not when ownership actually started).
  * `tos contact assign --station S --contact <id> --role owner --from DATE` — open a new relationship.
  * `tos contact remove <id_rel>` — delete a relationship (destructive;
    prefer `patch-relationship --time-to DATE` to end one).

**ACTION verbs** (triage-file form — batch with metadata fixes in one
`tos audit apply`, get the git provenance trail):

  * `ACTION <id_entity> patch-contact-relationship <id_rel> <field> <value>` — field ∈ {time_from, time_to, role}
  * `ACTION <id_entity> assign-contact <id_contact> <role> <time_from>`
  * `ACTION <id_entity> delete-contact-relationship <id_rel>`

The `id_entity` slot is the **station** (so the `start` date-token
resolves against the station's earliest_known — exactly the founding
date you backdate a migration artifact to). The migration-date fix is
literally `ACTION <station> patch-contact-relationship <id_rel>
time_from start`.

`patch_contact_relationship` GET-merges-PUTs (the admin endpoint is
PUT-replace): reads the current row, overlays the changed field, writes
the full row back. All three relationship write paths (PUT/POST/DELETE)
are live-verified against production TOS.

**`tos audit contact-dates <STN>`** — flags relationships whose
`per_time_from` is a TOS-migration artifact. The signal is a
**non-midnight time-of-day** (genuine ownership-start dates are at
`T00:00:00`; migration bulk-loads carry a real clock time, identical
within each batch — e.g. 26 relationships all at `2025-02-04T15:32:38`).
`--triage` emits commented `#ACTION <station>
patch-contact-relationship <id_rel> time_from start` lines (backdate to
the station's earliest_known). SUPPRESS file
`data/audit_suppressions/contact_dates.txt` (key `SUPPRESS
<id_relationship>`). Standalone cleanup audit — migration artifacts are
a one-time fixup, so it's not in the recurring verify oracle.

**Contact-entity writes** (`id_contact`, distinct from the relationship):

  * `tos contact create --name "…" [--organization …] [--phone …] [--email …] [--address …] [--start-date DATE] [--ssid …]` — new contact entity (`POST /contacts`). Returns the new id_contact, then `tos contact assign` maps it to a station. Dry-run default.
  * `tos contact patch-entity <id_contact> [--name …] [--phone …] …` — edit a contact (`PUT /contact/{id}/`, GET-merge-PUT). **FLEET-GLOBAL** — one contact serves many stations, so the change propagates everywhere.

There is **no contact-delete endpoint**: a created contact can't be
removed, only deactivated via `--end-date`. Contact-entity writes are
dry-run validated (body inferred from the GET shape like
`/contact_joins`); verified on first genuine use since no throwaway can
be cleaned up. The contact-write stack is now complete (relationship
CRUD + entity create/edit + the contact-dates audit).
