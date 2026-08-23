# The `tos` / `tosGPS` surface — as implemented

The design rule for the split (entity layer vs GPS interpretation layer) is in
`CLAUDE.md`. This page records **what the surface actually is** after the split
was completed, and how a new verb joins it.

## Every `tos` verb is reachable from `tosGPS`

`tosGPS` no longer has a partial, hand-maintained subset of `tos`'s verbs. Nine
verbs are shared, and they divide into exactly two kinds.

### Eight plain aliases

These delegate to `tos` unchanged — same arguments, same output, same exit
codes. `tosGPS audit …` *is* `tos audit …`.

| Verb | Why it is reached from a GPS task |
|---|---|
| `audit` | the audit family, run against a GPS station |
| `fleet` | fleet-wide GPS station enumeration |
| `station` | the station entity itself |
| `device` | exactly the subtypes the GPS profile curates |
| `location` | the required `land` parent of a station |
| `visit` | vitjanir hang off a station or device |
| `contact` | reached from `station show`'s Contacts table |
| `owners` | the allow-list backing `device add` |

They live in one table, `_PLAIN_ALIASES` in `tosGPS.py`, and are intercepted
before argparse:

```python
if verb and verb[0] in _PLAIN_ALIASES:
    from . import tos as _tos
    return getattr(_tos, _PLAIN_ALIASES[verb[0]])(sys.argv[2:])
```

### One profiled verb — `search`

`search` is the **only** verb with unconstrained behaviour worth narrowing. Under
`tosGPS` it is GPS-profiled: the subtype is pinned and non-GPS attributes are
refused. Under `tos` it is the general fleet query — see
[`search-selectors.md`](search-selectors.md).

Of the nine shared verbs, exactly one needed a profile; the rest are GPS-bound
by construction. The split bgo described was already true, just unnamed.

## Adding a verb

A new `tos` verb must be added to `_PLAIN_ALIASES` (or given a profile) or it
will not be reachable from `tosGPS`. **A test enforces this**: it asserts that

```
set(_PLAIN_ALIASES) | {"search"} == tos.KNOWN_SUBCOMMANDS
```

so a forgotten verb fails the suite rather than silently going missing. If you
add a verb and the suite fails there, that is the check doing its job — decide
whether the verb is a plain alias or needs a GPS profile, don't just widen the
assertion.

## `tos audit version-chains`

Septentrio receivers carry **one physical quantity on two attribute codes** —
`firmware_version` and `software_version`. Every writer except
`cfg add-receiver` touches firmware only, so software drifts. Nothing compared
them until this verb, and `tos station verify` reported clean on chains that
were years stale. It is not cosmetic: `software_version[:6]` is the SwVer
column of GAMIT `station.info`.

```bash
tos audit version-chains VMEY
tos audit version-chains --id <ID_ENTITY> --json
```

Exit 0 clean, 1 divergence found.

Two properties that matter:

- **Period-aware.** Comparing only the open period misses a chain whose history
  diverged while its tip happens to agree — exactly how six stations were called
  clean in the 2026-08-22 sweep (HVEL, ISAK, KALT, NYLA, SENG, THNA).
- **Septentrio only.** On Trimble the two codes are genuinely different
  quantities, so those receivers are reported as **skipped**, not silently
  dropped.

See also the memory note `tos-firmware-software-dual-chain` for the repair
shapes (VALUE-ONLY / EXTEND / REBUILD) and why a blanket `--correct` is wrong.

## Site logs have one entry point

**`tostools.core.site_log.build_site_log` is the single entry point for IGS site
log generation.** Both `tosGPS sitelog` and the `receivers` M3G dissemination
path go through it; `receivers` keeps only a re-export shim.

This is load-bearing, not stylistic. There were three renderers at one point,
one of them documented as canonical while being dead, and the live one was the
module the prose called legacy. A fix applied to the wrong renderer looks
correct in review and changes nothing in production — which is how an empty
antenna serial reached M3G and 463 archived files.

Supporting pieces moved into `tostools` alongside it, so `receivers` never owns
a second copy:

| Piece | Home |
|---|---|
| `build_site_log` | `core/site_log.py` |
| `find_previous_site_log` (§0 chain) | `core/site_log.py` |
| `generate_igs_sitelog_filename` | `core/site_log.py` |
| agency resolver | `core/agencies.py` |
| `firmware_to_software` | `device.py` |

The dependency direction is fixed: **`receivers` depends on `tostools`, never
the reverse.** Anything shared moves *into* `tostools` and leaves a re-export
shim behind.

The renderer `build_site_log` actually calls is
`legacy.gps_metadata_functions.site_log` — see
[`architecture/legacy-fork-unification-plan.md`](architecture/legacy-fork-unification-plan.md)
before "tidying" that import.
