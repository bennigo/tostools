# Unifying the `legacy/` fork — scope and order

**Status**: scoped, not started. Written 2026-08-23 after the redundancy sweep
that deleted `legacy/gps_rinex.py` and the abandoned `tostools/cli/` package.

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
| `api/tos_client.py:307,651` | — | **legacy** |
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
- **`get_contacts`** (+37/−7) — top-level adds a hardcoded IMO fallback used
  when TOS returns no owners, including `"phone_primary": "5226000"` **without
  the `+354` prefix**. `gps-config-data/agencies.yaml` was corrected to
  `"+354 5226000"` precisely because the bare number is not dialable from
  outside Iceland. Check whether this fallback can reach a published site log
  before assuming the yaml fix covered everything.
- **`gps_metadata`** — top-level is the documented-deprecated synthesis chain
  with two named bugs; legacy is the same chain without the warning. Neither is
  the successor: `gps_metadata_via_devices` is.

**Order**: port `tos_client.py`'s two inline imports onto a single
implementation, diffing those two functions first; then delete
`legacy/gps_metadata_qc.py` once importer-free.

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
pinned rather than resolved. It is the natural place to assert the merged
behaviour.

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
