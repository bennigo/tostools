# Unifying the `legacy/` fork — scope and order

**Status**: F1 steps 1-3 done (2026-08-23); F1 step 4 blocked on F2; F2 not
started. Written 2026-08-23 after the redundancy sweep that deleted
`legacy/gps_rinex.py` and the abandoned `tostools/cli/` package.

> **Overlaps an untracked doc.** `docs/security-streamlining-remediation-plan.md`
> (untracked at time of writing) covers the same F1 ordering under its §T1. It
> reaches the same conclusion on `legacy/gps_rinex.py` but describes it as
> "~85 % identical — near-pure duplication", where the sweep established it was
> **stale**: no importer, and missing `domes_or_skip` plus the version
> comparator. Two plan docs disagreeing about one merge is the exact pattern
> this work exists to remove — reconcile or retire one before starting F1.

`src/tostools/{gps_metadata_functions,gps_metadata_qc}.py` and
`src/tostools/legacy/<same names>` are a **partially-completed modernization
fork**. The refactor was never finished, both copies stayed live, and fixes have
since landed on whichever side the author happened to be editing.

This is the same defect shape that produced the last three sessions' bugs — two
implementations of one thing, one quietly wrong — at the largest scale it exists
in this repo.

## Do not assume "modern is right"

The obvious reading — top-level is the new one, `legacy/` is the old one — is
**wrong**, and acting on it would delete working behaviour.

- The **live site-log renderer** is `legacy.gps_metadata_functions.site_log`
  (783 L), reached through `core.site_log.build_site_log`. The top-level
  `site_log` (608 L) is the stale one. A *third* renderer,
  `generate_igs_site_log`, was documented as canonical, was dead, and was
  deleted last session.
- Conversely, the top-level `gps_metadata_qc` holds `gps_metadata_via_devices`,
  the **new** synthesis chain, alongside a `gps_metadata` explicitly docstringed
  as deprecated (see `synthesis-legacy-divergence.md`). So one module contains
  both the newer and the older implementation.

Establish liveness by grepping call sites. Never by reading docstrings — the
prose consistently drifts toward the prettier module.

## Who reaches which fork today

| Call site | `gps_metadata_functions` | `gps_metadata_qc` |
|---|---|---|
| `core/site_log.py:117` | **legacy** | — |
| `tosGPS.py` | **legacy** (`gpsf`, line 24) | **top-level** (`gpsqc`, line 15) |
| `api/tos_client.py:307,651` | — | ~~legacy~~ → **top-level** (F1 steps 1-2) |
| `legacy/gps_metadata_functions.py:24` | — | **legacy** ← blocks step 4 |
| `__init__.py:21,22` | top-level | top-level |

Two consequences worth stating plainly:

1. **`tosGPS` builds station.info across both forks** — data from top-level
   `gpsqc.gps_metadata*`, rendered by legacy `gpsf.print_station_info`.
2. **`tostools.print_station_history` (the public API export) is not what the
   CLI runs.** `__init__` exports the top-level one (176 L); `tosGPS` calls the
   legacy one (161 L).

## F1 — `gps_metadata_qc` (do this one first)

1052 L top-level / 1005 L legacy. **13 shared functions, zero identical.**

Most of the divergence is one cosmetic refactor repeated per function:

```python
-    module_logger = gpsf.get_logger(name=__name__)   # legacy
-    module_logger.setLevel(loglevel)
+    module_logger = get_logger(__name__, loglevel)   # top-level
```

That accounts for the ±1/−2 line diffs in `additional_contact_fields`,
`device_structure`, `get_device_history`, `get_device_sessions`,
`get_station_metadata`, `main`, `search_station`, `getSession`. The
`read_gzip_file` / `read_text_file` / `read_zzipped_file` trio is the same story
— top-level delegates to `io/file_utils`, legacy inlines the body.

Three carry divergence that decides the merge. Note the first was initially
written up here as a live functional gap and was **wrong** — the diff showed a
missing attribute list, but the default runtime path reaches it elsewhere.
Check the call path, not the diff, before acting on any of these:

- **`device_attribute_history`** — legacy fetches the GNSS constellation toggles
  (`GAL`, `BDS`, `QZSS`, `SBAS`, `IRN`) and `azimuth` (commit `052d7f7`, which
  landed on legacy only); the top-level copy does not.

  **This is a duplicated constant, not a missing capability** — do not read the
  diff as a live gap. `tosGPS` defaults to `gps_metadata_via_devices` →
  `devices.station_sessions`, and `devices.SITELOG_GPS_ATTRIBUTE_CODES` carries
  the constellations and `azimuth` itself; its own comment says it "Mirrors the
  legacy `gps_metadata_qc.device_attribute_history` key_list". So the attribute
  list now exists in **two** places that must be changed together, and the
  top-level `device_attribute_history` is short only on the **deprecated**
  `gps_metadata` chain (the `--use-legacy-synthesis` opt-out).

  The merge job here is therefore to collapse the mirrored list onto
  `devices.SITELOG_GPS_ATTRIBUTE_CODES`, not to "restore missing attributes".
  **Done in step 2** — and the write-up above understated it in one respect:
  the list was hardcoded in *three* places, not two (both forks plus the
  constant), which is why "change them together" had already failed.
- **`get_contacts`** (+37/−7) — top-level adds a hardcoded IMO fallback used
  when TOS returns no owners, including `"phone_primary": "5226000"` **without
  the `+354` prefix**. `gps-config-data/agencies.yaml` was corrected to
  `"+354 5226000"` precisely because the bare number is not dialable from
  outside Iceland. Check whether this fallback can reach a published site log
  before assuming the yaml fix covered everything.
- **`gps_metadata`** — top-level is the documented-deprecated synthesis chain
  with two named bugs; legacy is the same chain without the warning. Neither is
  the successor: `gps_metadata_via_devices` is.

### The F1 trap, traced 2026-08-23 — resolved 2026-08-23, kept as the record

> **Resolved by step 2** (`d467807` + `5977574`). The import below now points at
> the top-level module, which is safe only because the attribute list was
> collapsed onto one definition first. Kept in full because the trap explains
> the ordering, and because the same shape recurs in F2.
>
> **One claim below is overstated — corrected 2026-08-23 by tracing the callers.**
> A naive repoint would NOT have dropped §3.3/§4 "out of every published site
> log". Those sections are composed by `devices.device_sessions`
> (→ `slice_attributes_by_window`), which never calls `device_attribute_history`:
> `site_log` builds its own sessions whenever `device_sessions=` is not passed,
> and **no production caller passes it** — `core.site_log.build_site_log`, the
> single entry point for both `tos sitelog` and receivers' EPOS dissemination,
> never does.
>
> What the repointed chain actually feeds: §11/§12/§13 agency resolution
> (`build_site_log` calls `get_complete_station_metadata` for that alone),
> `_build_history_from_connections`, and every receivers consumer of
> `get_complete_station_metadata` — `cfg reconcile`, `tos_adapter`, `tos_push`,
> `stream_scheduler`, `streaming/skeleton`, `dissemination/tos_access`.
>
> The ordering was still right and the hazard still real — a dropped attribute in
> those station-metadata dicts is exactly as invisible as one in a site log, and
> lands in config reconciliation instead. But the blast radius named below is
> wrong, and F2 will inherit this map, so: **verify the renderer's input path
> before trusting any claim in this document about what reaches a published log.**

`api/tos_client.py:651` is **on the site-log publishing path**:

```
core/site_log.py:127   client.get_complete_station_metadata(sid)
  -> tos_client.py:253   self.get_device_sessions(device_history)
    -> tos_client.py:630   self._get_device_attribute_history(...)
      -> tos_client.py:651   from ..legacy.gps_metadata_qc import device_attribute_history
```

That legacy copy is the one whose `key_list` carries `GAL`/`BDS`/`QZSS`/`SBAS`/
`IRN` and `azimuth`; the top-level copy does not. **Swapping this import to the
top-level `gps_metadata_qc` would silently drop §3.3 Satellite System and §4
Alignment from True N out of every published site log** — and the loss would look
like a metadata gap, not a code regression, so it would be diagnosed on the wrong
side for a long time.

`device_structure` (`tos_client.py:307`) has no such hazard: its only divergence
is the `get_logger` shim, so that one is a safe swap.

**Order**:

1. ~~Swap `device_structure` to the top-level copy — behaviour-identical, verify
   by diff.~~ **DONE 2026-08-23** (`6b8657c`). The two bodies differed only in
   how the module logger is built, and the function calls nothing that itself
   diverges. Differential-tested across all 8 `code_entity_subtype` branches ×
   4 numeric inputs (including `""`, so the `float()` failure mode is compared
   too): 32/32 identical, exceptions included. Pinned by
   `tests/test_f1_device_structure_unified.py`, whose guards are
   mutation-tested — and which also asserts step 2 has **not** been done by
   analogy.
2. ~~For `device_attribute_history`, do **not** swap. First collapse the attribute
   list onto `devices.SITELOG_GPS_ATTRIBUTE_CODES` (which already carries the
   constellations and `azimuth`, and whose comment says it mirrors this very
   `key_list`), so one definition feeds both. Only then repoint the import.~~
   **DONE 2026-08-23** (`d467807` collapse, `5977574` repoint — two branches,
   in that order). Both copies now take `codes=` and **default** to
   `SITELOG_GPS_ATTRIBUTE_CODES`. The default placement was deliberate: passing
   the wide list from the call site instead would have left the trap armed for
   the next caller. The constant is element-for-element the legacy `key_list`
   minus the two bookkeeping keys the kernel appends itself.
3. ~~Pin the result with a test that a generated site log still populates §3.3 and
   §4 for a station with non-GPS constellations.~~ **DONE** —
   `tests/test_f1_device_attribute_history_unified.py`.

   Two things that test had to get right, both of which a plausible-looking
   test gets wrong:

   - It drives the **real** chain (TOS attribute rows → `get_device_sessions`
     → `site_log`), stubbing only `_make_request`. The renderer's
     `device_sessions=` injection seam — which the other offline site-log tests
     use — bypasses `device_attribute_history` entirely, so a fixture built on
     it passes identically with the narrow key list restored.
   - It asserts on the extracted **subsection**, never on the whole log. Every
     section ends with an instruction block whose §3.x placeholder text is
     literally `(GPS+GLO+GAL+BDS+QZSS+IRNSS+SBAS)`, so `"GPS+GLO+GAL" in log`
     is true even when the real subsection has fallen back to a bare `GPS`.

   Verified by mutation both before and after the repoint (restoring the narrow
   list turns the guards red on whichever copy is live at the time), and by
   byte-identity: the full 267-line rendered log matches one produced from a
   worktree at `848cca4`.

   **Both of those render through `site_log(device_sessions=…)`, which no
   production caller uses** (see the corrected trap note above). The guard on
   the path production DOES take asserts on `get_device_sessions` output
   directly — `TestDeviceSessionsKeepConstellationsAndAzimuth`. The site-log
   assertions were written to the overstated claim and are kept, relabelled, as
   a check that the two session producers stay interchangeable at the renderer's
   input.

   One measured behaviour worth carrying into F2: `codes` is not just a filter.
   It gates `if item["code"] in key_list`, so a widened list lets more attribute
   rows move `date_from`/`date_to`. On a device with a GAL toggle starting
   mid-tenure the session start moves ONTO the toggle date and the pre-GAL
   period vanishes — this kernel's documented Bug 1
   (`synthesis-legacy-divergence.md`), pre-existing on the legacy copy and the
   reason the renderer uses the newer slicer. Pinned by
   `test_widening_the_codes_moves_period_boundaries_not_just_keys`.
4. Delete `legacy/gps_metadata_qc.py` once importer-free. **Not yet reachable —
   and it is not blocked on step 2.** `api/tos_client.py` no longer imports it,
   but `legacy/gps_metadata_functions.py:24` still does, at module level, and
   that module is the **live site-log renderer**. It uses five other symbols
   from the legacy copy — `search_station`, `get_station_metadata`,
   `URL_REST_TOS`, `wgs84toitrf08`, `get_device_sessions` — every one of which
   also exists in the top-level module. So step 4 is **coupled to F2**, not
   free-standing: the deletion lands when the renderer migrates, not before.
   The only other importers are the transitional differential tests, which are
   meant to die with the file.

Steps 1-2 are separate branches; do not bundle them.

## F2 — `gps_metadata_functions` (separate session, after F1)

1551 L top-level / 1814 L legacy. 17 shared, 9 diverged, and the diverged ones
are large and semantic — not the logging shim:

| function | diff | note |
|---|---|---|
| `site_log` | +301/−476 | the live renderer is **legacy**; top-level is stale |
| `print_station_info` | +194/−140 | `tosGPS` calls **legacy** |
| `print_station_history` | +28/−13 | public API ≠ CLI, see above |
| `get_monument_height` | +8/−9 | check before assuming cosmetic |
| `get_data_file_path` | +5/−14 | packaging-sensitive, see `data_files.data_path` |
| `get_radome`, `domes_info_form`, `file_list`, `getSession` | small | likely the logging shim |

legacy-only: `_fmt_igs_date`, `_igs_agency_section`, `get_logger`,
`normalize_icelandic_for_gamit`, `satellite_system_from_toggles`.

This is a **migration, not a delete** — `tosGPS.py:24` and `core/site_log.py`
both depend on the legacy module, and the surviving `site_log` is the 783-line
one. Do not bundle F2 with F1.

## Tests that must move, not die

Three tests pin behaviour to `legacy.gps_metadata_functions` **by name**, and
one (`test_sitelog_unknown_antenna_serial.py:124`) asserts on the literal import
line as source text. They were deliberately re-pinned to the live path last
session and are the only guard on the synthetic-serial and `0000` rules:

- `tests/test_sitelog_unknown_antenna_serial.py`
- `tests/test_synthetic_serial_not_published.py`
- `tests/test_site_log_legacy_unify.py`

`tests/test_device_attribute_history_none_date.py` already imports **both**
implementations (`dah_current` + `dah_legacy`) — the divergence was noticed and
pinned rather than resolved. Its parametrization over both copies still holds
and is left alone; the merged-behaviour assertion went into the new
`tests/test_f1_device_attribute_history_unified.py` instead, so the DYNC
regression test keeps stating one thing.

Both `test_f1_*_unified.py` files carry a `TestTheTwoCopiesStillAgree` class
that is **transitional by design** — it exists only while both copies do, and
should be deleted along with `legacy/gps_metadata_qc.py` in step 4 rather than
migrated.

## Smaller items found in the same sweep

- The GAMIT `station.info` header string is duplicated three times
  (`tosGPS.py`, `gps_metadata_functions.py`, `legacy/gps_metadata_functions.py`).
  A fourth copy went with `tostools/cli/main.py`. It is a format spec and
  belongs in one place.
- `gps_metadata_functions.py:1194` and its legacy twin at :1427 contain
  `phone_primary = +354 + phone_primary` — unary plus on an int, then `int + str`.
  It cannot fire today only because `contact = {}` two lines above guarantees the
  guard is never entered. Latent `TypeError` if that branch is ever populated.

## Ruled out — similar names, different jobs

Checked for shared function names, found **zero** in each case; these are not
duplicate pairs and should not be swept:

`device.py` / `core/device.py` · `station.py` / `core/station.py` ·
`archive.py` / `utils/archive.py` · `owners.py` / `legacy/owner.py` ·
`audit_firmware_chain.py` / `audit_version_chains.py` (shares only the common
name `format_report`)
