# Security & Streamlining Remediation Plan — tostools (2026-08-17)

Companion to `receivers/docs/security-streamlining-remediation-plan.md`. Same
shape: **S** = security, **T** = streamlining. **Goal: execute the fixes.** This
doc is the durable hand-off across a `/clear`. Paths relative to `src/tostools/`.

## Scope and coverage — read this before trusting the list

`tostools` is 69 files / 51,248 lines. This pass was **targeted, not exhaustive**:
pattern sweeps for the known dangerous constructs, then manual inspection of every
hit. What that covers well: the injection/transport/subprocess classes, credential
handling, and the large-scale duplication. What it does NOT cover: per-function
logic review of `tos.py` (14,066 lines) and `tosGPS.py` (4,757), the 12 `audit_*`
modules' domain correctness, or the RINEX parsing edge cases. Treat an empty
finding in an unreviewed area as *unknown*, not as *clean*.

## What came back CLEAN (recorded so nobody re-derives it)

These were checked across all of `src/` and produced **zero** hits. They are the
findings that dominated the `receivers` review, so their absence here is the main
structural result:

| Class | Result |
|---|---|
| TLS bypass (`verify=False`, `CERT_NONE`, `check_hostname=False`) | none |
| Shell injection (`shell=True`, `os.system`) | none |
| Code execution (`eval`, `exec`, `pickle.load`, unsafe `yaml.load`) | none |
| Archive extraction (zip/tar-slip, `extractall`) | none — no archive extraction at all |
| SQL injection | **not applicable** — no `psycopg2`, no `execute()`, no DB layer. tostools is a pure REST client. This removes the entire class that produced S1/S2/S8 in `receivers`. |
| Credentials in log output | none — `tos_writer.py:368,402` log *about* the token, never its value |
| HTTP calls without timeout | none in live code (all use `REQUEST_TIMEOUT` / `self.timeout`); one dead-module exception, see S3 |

**Do not re-run these sweeps.** The one-line greps report false positives on
multi-line calls — every `requests.*(` hit in this repo looked timeout-less on
line 1 and had `timeout=` two to five lines down.

---

## S1 (MED) — subprocess calls with no timeout, over an NFS archive

Five call sites spawn external binaries with no `timeout=`. On a local disk this
is a minor robustness gap; here it is not, because the archive these run against
is `/mnt/rawgpsdata` — an NFS mount (`ananas.vedur.is:/gps/gpsdata`) currently at
**96 % full**. A stalled NFS read blocks in uninterruptible sleep indefinitely,
and these run in batch over hundreds of thousands of files during retrofits.

| Site | Command | Notes |
|---|---|---|
| `rinex/corrector.py:671` | `zcat <archive .Z>` | **highest value** — sits in the header-correction path every retrofit run drives |
| `rinex/corrector.py:714` | `compress -f` | same path, write side |
| `io/file_utils.py:76` | `zcat` fallback | shared `.Z` reader for header QC |
| `receiver_timeline.py:170` | `gzip -dc` (Popen) | **partially mitigated** — see below |
| `tos.py:12586` | `git -C … rev-parse` | local, fast; lowest priority |

`receiver_timeline.py` deserves credit and is still a finding: its `finally`
block does `stdout.close()` → `terminate()` → `wait(timeout=5)` → `kill()`, which
is exactly right. The gap is that the unbounded `proc.stdout.read(4096)` loop can
block *before* control ever reaches that `finally`. Correct cleanup does not save
you from a read that never returns.

**Fix:** add `timeout=` to the four `subprocess.run` sites; for the `Popen`, bound
the read loop (deadline check per chunk, or `communicate(timeout=…)`). Adopt the
`receivers` convention so the two repos agree. ⚠️ The `receivers` lesson applies:
killing the launcher can orphan the worker — kill the **process group**, not the
pid (see `receivers` `fix/converter-timeout-kills-process-group`).

## S2 (LOW) — bare `except:` swallows control-flow exceptions

12 sites. A bare `except:` catches `KeyboardInterrupt` and `SystemExit`, so a
long retrofit cannot be interrupted cleanly at those points, and genuine bugs are
masked as data problems.

`gps_metadata_qc.py:859`, `gps_metadata_functions.py:167,544,550`,
`tosGPS.py:4590`, `legacy/owner.py:27`, `legacy/gps_metadata_qc.py:777`,
`legacy/gps_metadata_functions.py:203`, + 4 more (`grep -rn "except:" src/`).

Separately, 8 sites are `except Exception: … pass`. Each needs a one-line reason
or a narrower type.

**Fix:** `except Exception:` at minimum; narrow where the failure mode is known.
Mechanical, but do it per-module with eyes on — some of these are load-bearing
fallbacks for genuinely malformed archive files.

## S3 (LOW) — `legacy/owner.py` performs a network call at import time

`legacy/owner.py:14` issues `requests.get()` against a hardcoded production URL
(`https://vi-api.vedur.is:11223/tos/v1`) **at module scope**, with no timeout, for
a hardcoded `id_entity_parent: 4392`, and swallows the result in a bare `except:`.
Importing this module does I/O and can hang forever.

It appears to be an unported script fragment: no import of it exists anywhere
(`grep` over `src/` finds none). But `legacy/` as a package **is** live (see T1),
so this file is one careless `from ..legacy import owner` away from being armed.

**Fix:** delete the file. Confirm zero importers first.

---

## T1 — `legacy/` duplicates the modern modules, and is still load-bearing

> **Superseded — T1 is owned by
> [`architecture/legacy-fork-unification-plan.md`](architecture/legacy-fork-unification-plan.md).**
> That doc carries the current call-path map, the per-function divergence
> measurements, and the merge order. Do not plan T1 from this section; two plans
> disagreeing about one merge is the defect class T1 exists to remove. The
> summary below is kept only so this doc's execution order still reads.

**Partly done.** The 2026-08-23 redundancy sweep deleted, after proving each
importer-free:

- `legacy/gps_rinex.py` — **1,168 lines.** This section originally called it
  "~85 % identical — near-pure duplication", which understated it: it had **no
  production importer at all**, and it was **stale**, never having received
  `domes_or_skip` (the MARKER NUMBER / IERS DOMES policy, `6d23524`) or the
  receiver version comparator (`7a24eed`). A dead copy of the RINEX writer that
  had silently missed two shipped policies — not merely a duplicate.
- `tostools/cli/` — 293 lines, an abandoned re-implementation of `tosGPS`; not
  in `[project.scripts]`, zero importers.

**Still open**, and the reason the fork plan exists: two modules remain live on
*both* sides, with fixes having landed on whichever side was in view.

| module | top-level | legacy | shared functions | identical |
|---|---|---|---|---|
| `gps_metadata_qc` | 1052 | 1005 | 13 | **0** |
| `gps_metadata_functions` | 1551 | 1814 | 17 | 8 |

Three sites still import from `legacy/`:

- `tosGPS.py:24` — `from .legacy import gps_metadata_functions as gpsf` (module-level)
- `api/tos_client.py:307` — `from ..legacy.gps_metadata_qc import device_structure` (inline)
- `api/tos_client.py:651` — `from ..legacy.gps_metadata_qc import device_attribute_history` (inline)

Note the direction is **not** "modern good, legacy old": the live site-log
renderer is `legacy.gps_metadata_functions.site_log`, and the top-level copy is
the stale one. See the fork plan before assuming which side survives.

**Order:** (1) port the two `tos_client.py` inline imports onto one
implementation, diffing those functions first; (2) delete
`legacy/gps_metadata_qc.py` once importer-free; (3) treat
`legacy/gps_metadata_functions.py` + `tosGPS.py` as a separate, later migration.
Do **not** bundle (3) with (1)-(2).

## T2 — file sizes past the point of navigability

- `tos.py` — **15,327 lines** (14,066 when reviewed on 2026-08-17; it has grown
  since, which argues for T2 rather than against it). Larger than anything in
  `receivers` (whose worst was `cli/cfg.py` at 7,645, itself slated for a split
  as T5 there).
- `tosGPS.py` — 4,756.
- `api/tos_writer.py` — 2,393.

`tos.py` is the CLI surface for every verb documented in `receivers/CLAUDE.md`
(`tos device`, `tos station`, `tos audit`, `tos visit`, `tos fleet`, …), so the
natural seam is per-verb modules mirroring the `receivers` `cli/cfg_cmds/<verb>.py`
plan. **This is the highest-risk item in the doc and belongs last**, after S1-S3
and T1 have settled the code it would move.

## T3 — 12 `audit_*` modules with no shared scaffold (needs measurement)

`audit.py`, `audit_arbitrate.py`, `audit_attribute_dates.py`,
`audit_constellations.py`, `audit_contact_dates.py`, `audit_duplicate_serials.py`,
`audit_firmware_chain.py`, `audit_fleet_sweep.py`, `audit_missing_attributes.py`,
`audit_reconstruct.py`, `audit_rinex_timeline.py`, `audit_verify_from_rinex.py`,
`audit_visit_coverage.py`.

They share an obvious shape (run per station, emit findings, feed `tos audit
apply` triage files), which is exactly the pattern that accumulates copy-pasted
finding-emission and station-iteration code. **Not yet measured** — unlike T1,
there is no diff evidence here yet. Quantify the overlap before committing to a
shared base class; the numbers in T1 came out very differently per module and
this will too.

---

## Execution order

S3 → S2 → S1 → T1(1-2) → T3(measure) → T1(3) → T2.

S3 first because it is a single file deletion that also shrinks T1's surface.
S1 is the one with production consequence, but it wants the `receivers`
process-group convention settled first so both repos land the same fix.

**Mechanics** (same as the `receivers` plan): one branch per item off `master`
(**note: tostools' default branch is `master`, not `main`**), then `ruff` +
`black` + `mypy` + `pytest` with explicit file args, review, merge. tostools is
editable-installed in the `gpslibrary` mamba env, so a merge is live on the
laptop immediately — and `tos` verbs write to **production TOS**. Dry-run
everything.

## Status tracker

| Item | State |
|---|---|
| S1 subprocess timeouts | not started |
| S2 bare excepts | not started |
| S3 `legacy/owner.py` | not started |
| T1 legacy dedup | **partly done** — `legacy/gps_rinex.py` + `tostools/cli/` deleted 2026-08-23; the two live forks are owned by [`architecture/legacy-fork-unification-plan.md`](architecture/legacy-fork-unification-plan.md) |
| T2 `tos.py` split | not started (now 15,327 lines) |
| T3 audit scaffold | not measured |

---

*Review performed 2026-08-17. Companion: `receivers/docs/security-streamlining-remediation-plan.md`
(Group 1 landed + deployed 2026-07-27; Groups 2-5 pending).*
