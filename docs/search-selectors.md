# `tos search` — the selector language

`tos search` queries the TOS fleet by station attributes and by the devices
currently joined to a station. This page is the reference for the expression
grammar; `tos search --help` is the same material in terse form.

**Default scope**: `subtype = GPS stöð` is applied automatically. Lift it with
`subtype = all`, or name types explicitly: `subtype = [GPS stöð, SIL stöð]`.

Expressions test the **currently-open attribute period** — the value the TOS
UI's *Eigindi* panel shows today — unless `--at` or `--history` says otherwise.

## Expressions

Positional, repeatable, AND-ed.

| Form | Meaning |
|---|---|
| `code = value` | equality, case-insensitive; `já`/`nei` fold onto `true`/`false` |
| `code != value` | not equal — **an absent value also satisfies `!=`** |
| `code ~ text` | text match, see Patterns |
| `code !~ text` | negated text match |
| `code = null` | attribute absent / no open period |
| `code != null` | attribute present |
| `code = [a, b]` | value is one of |
| `code != [a, b]` | value is none of |
| `code = all` | match everything — lifts a scope filter |

## Patterns — `~` and `!~` only

`=` always stays exact. On the match operators:

- **plain text** — substring: `'marker ~ ve'`
- **`* ? [ ]`** — glob, and **fully anchored**. `'marker ~ HVE*'` is
  *starts-with*, not contains. For substring, wrap in stars: `'name ~ *vík*'`
- **`re:PATTERN`** — regex, unanchored: `'name ~ re:vík|dal'`

A term is never treated as a regex unless it says `re:`, so `'name ~ a.b'`
still means a literal `a.b`.

## Selectors

A bare code addresses a **station** attribute. A dotted selector addresses an
attribute of a **currently-joined device**:

```
receiver.firmware_version     the station's GNSS receiver
antenna.serial_number
*.model                       a device of any subtype
```

The namespace takes the same aliases as `--device TYPE:MODEL` (`receiver`,
`antenna`, `radome`, `monument`, `modem`, `sim`, `router`). Selectors work both
in expressions and in `--show`:

```bash
tos search --receiver polarx5 \
    --show receiver.firmware_version,receiver.software_version

tos search 'receiver.firmware_version ~ 5.7*'
```

Two behaviours worth knowing before trusting a result:

- **Cost** — a device selector triggers the per-station device walk, so it costs
  what `--receiver` / `--device` cost (~1 + N_children HTTP calls per surviving
  station; fleet-wide is ~30–60 s). Narrow with **station** predicates first;
  those prune the fleet *before* the walk.
- **Aggregation is existential** — a station matches when ANY device in the
  namespace satisfies the predicate. On a two-receiver station,
  `'receiver.firmware_version != 5.7.0'` means "has a receiver that is not on
  5.7.0", not "has no receiver on 5.7.0". Every device in the namespace
  contributes to a `--show` cell, comma-joined.

## Time — `--at` and `--history`

- `--at YYYY-MM-DD` — evaluate every selector as of that date instead of today;
  the period covering the date wins. Makes "who ran 5.3.0 in June 2021"
  answerable.
- `--history` — one row per period instead of one row per station, with FROM/TO
  columns. **Filters become existential over time** — "ever held this value"
  rather than "holds it now". Rows are segmented at the union of every selected
  column's change dates, so columns that move on different dates stay correct.

Mutually exclusive.

## Caching and snapshots

Device selectors cost one history call per station, so an iterative session
re-pays that without the cache.

| Flag | Effect |
|---|---|
| `--cache-ttl SECONDS` | how long a cached read stays fresh (default 900) |
| `--no-cache` | bypass entirely — neither read nor write |
| `--refresh` | ignore cached entries, re-fetch, refill |
| `--snapshot FILE` | record everything this run reads from TOS |
| `--from-snapshot FILE` | replay a snapshot, **no network at all** |

Every run that serves a cache hit reports the age of its oldest entry.

A snapshot covers exactly what its query walked, so **take it with the widest
query you intend to replay** — a lookup the file does not contain is an error,
not an empty result. The recording time is always printed, which is what makes
a snapshot usable as a dated audit artifact.

## Discovery

Do this before writing a predicate rather than guessing at codes:

```bash
tos search --attribute-list                      # what codes exist
tos search --attribute continuity --allowed-values   # what values it takes
tos search --selectors                           # the index
tos search --selectors receiver                  # one subtype's attributes
tos search --selectors all --observed
```

`--selectors` asks for ONE thing at a time: `station`, `subtypes`, a subtype
name, or `all`. Every line starts with the selector exactly as `tos search`
expects it, so output pastes straight into the next command; `--json` emits a
bare array.

`--observed` additionally reads what the live fleet actually carries rather than
what the catalog classifies. It costs a device walk (cached) and is the **only**
source for `modem` / `sim` / `router`, which the catalog says nothing about.

## Sugar flags

`--epos`, `--no-epos`, `--active-gps`, `--discontinued`, `--continuous`,
`--campaign`, `--no-ice` expand to ordinary expressions and compose with
everything else. `--active-gps` is the operational IMO GNSS fleet:
`subtype = GPS stöð`, `date_end = null`, `geological_characteristic != ice`,
`continuity = continuous`.

## Examples

```bash
tos search --epos
tos search --active-gps --no-receiver          # operational fleet, no receiver
tos search --discontinued --markers-only
tos search 'iers_domes_number != null'
tos search --epos --receiver polarx5 --show iers_domes_number
tos search --device router:any --device sim:any
tos search 'subtype = all' --markers-only
tos search --json --epos > epos.json
```

Output modes: `--json`, `--markers-only` (one 4-char marker per line,
pipe/xargs friendly), `--limit N`.
