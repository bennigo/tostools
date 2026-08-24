# `tos search` — the selector language

`tos search` queries the TOS fleet by station attributes and by the devices
currently joined to a station. This page is the reference for the expression
grammar; `tos search --help` is the same material in terse form.

**Default scope**: none. `tos search` is the entity layer and spans every
subtype in the domain — 443 geophysical entities across 17 subtypes, not the
217 GPS stations alone. Narrow with `subtype = GPS stöð`, or name several:
`subtype = [GPS stöð, SIL stöð]`. `--domain` picks geophysical (default),
meteorological or hydrological.

For GPS work use **`tosGPS search`**, which pins `subtype = GPS stöð` and
refuses attributes the GPS group does not curate — see
[`cli-surface.md`](cli-surface.md). That pin is why this command no longer
carries one: until 2026-08-24 `tos search` applied a silent GPS default, which
made the entity-layer/GPS-layer split untrue. `subtype = all` still parses and
still matches everything; it is now a no-op rather than a scope lift.

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

## Visit selectors — `visit.*`

A `visit.` selector addresses the station's **vitjanir** (visit / maintenance
records), a list-per-entity rather than a single value. Available fields:

| Selector | Matches |
|---|---|
| `visit.work` / `visit.comment` / `visit.remaining` | that note field (Vinna / Athugasemdir / Útistandandi) |
| `visit.all` (aliases `visit.any`, `visit.text`) | **any** of the three note fields |
| `visit.type` | `maintenance_type` — `on_site` / `remote` |
| `visit.participants` | email **or** resolved name |

Aggregation differs from devices in one important way — **multiple POSITIVE
visit predicates group onto ONE visit** (`visit.work ~ TOS` + `visit.type =
remote` = a remote visit whose work matches), and the **negated operators are
UNIVERSAL**: `visit.work !~ X` means *no visit* whose work matches X, the
inverse of the include form. `= null` is universal absence, `!= null`
existential presence. A visit selector walks the vitjun list (one call per
surviving station, after station predicates prune the fleet).

```bash
tos search --epos 'visit.all ~ "TOS reviewed"'    # onboarded

tos search --epos 'visit.all !~ "TOS reviewed"'   # still to do

tos search 'visit.type = remote' 'visit.participants ~ bgo'

tos search 'visit.remaining != null'              # stations with open items
```

## Contact selectors — `contact.*`

A `contact.` selector addresses the station's **contacts** — the owner /
operator / data-owner organisations that live in the contact roles
(Eigandi stöðvar / Rekstraraðili / Eigandi gagna), *not* the `owner` attribute
(which only carries IMO/Cambridge/Czech/ÍSOR).

| Selector | Matches |
|---|---|
| `contact.owner` / `contact.operator` / `contact.data_owner` | that role's organisation |
| `contact.organization` / `contact.name` / `contact.email` | any contact's field |

Organisation terms get **abbreviation expansion** from `agencies.yaml`, so
`contact.owner ~ IES` resolves to `Jarðvísindastofnun Háskóla Íslands` without
knowing the Icelandic genitive. Negation is universal — `contact.owner !~ IES`
means the owner org does not match (exclude an agency). Sugar:
`--owner ORG` / `--no-owner ORG`.

```bash
tos search --epos 'contact.owner !~ IES'     # exclude the IES stations

tos search --no-owner IES                    # same, as a flag

tos search --owner Cambridge                 # only Cambridge-owned
```

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
tos search --selectors visit                     # visit.* vocabulary
tos search --selectors contact                   # contact.* vocabulary
tos search --selectors all --observed
```

`--selectors` asks for ONE thing at a time: `station`, `subtypes`, `visit`,
`contact`, a subtype name, or `all`. Every line starts with the selector
exactly as `tos search` expects it, so output pastes straight into the next
command; `--json` emits a bare array.

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
tos search --markers-only                      # every subtype in the domain
tos search 'subtype = GPS stöð' --markers-only  # narrow to GPS
tos search --json --epos > epos.json
tos search --epos 'visit.all ~ "TOS reviewed"'   # onboarded
tos search --epos 'visit.all !~ "TOS reviewed"'  # still to do
tos search --epos 'visit.all !~ "TOS reviewed"' --no-owner IES  # minus IES
tos search --owner Cambridge                   # only Cambridge-owned
```

Output modes: `--json`, `--markers-only` (one 4-char marker per line,
pipe/xargs friendly), `--limit N`.
