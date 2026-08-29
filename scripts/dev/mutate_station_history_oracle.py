#!/usr/bin/env python3
"""Mutation-test the station-history oracle (F2 step 2).

    python3 scripts/dev/mutate_station_history_oracle.py

Run after ANY change to `print_station_history`, its `legacy` delegator, or
`tests/test_station_history_oracle.py`. Exits non-zero and names survivors.

Same contract as `mutate_sitelog_oracle.py` — see that file's header for the
stale-bytecode and ambiguous-anchor traps, and for why `resnapshot=True`
exists (it regenerates snapshots FROM the mutated code so the byte-compare is
satisfied by construction and only genuine structural guards can still fail).

What this file adds over the site-log one: F2 step 2 unified two copies onto
the WORKING implementation and introduced a user-facing language option, so
the guards worth breaking are the delegation itself and the language
selection — not just rendered bytes.
"""

import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
IMPL = REPO / "src/tostools/gps_metadata_functions.py"
LEGACY = REPO / "src/tostools/legacy/gps_metadata_functions.py"
ORACLE = "tests/test_station_history_oracle.py"
SNAPSHOTS = REPO / "tests/_oracle_outputs/station_history"
SNAPSHOT_BACKUP = REPO / "tests/_oracle_outputs/.station_history_backup"
PP = str(REPO.parent / "receivers/scripts/dev")
PYTHON = sys.executable

# (name, old, new, -k selector, resnapshot, target file)
MUTATIONS = [
    (
        # The unification itself. If the legacy delegator stops reaching the
        # working implementation, tosGPS silently goes back to the crashing
        # copy — the exact regression F2 step 2 exists to prevent.
        "the legacy delegator stops reaching the working implementation",
        "    from ..gps_metadata_functions import print_station_history as _live",
        "    from ..gps_metadata_functions import print_station_info as _live",
        "test_the_route_tosGPS_takes_renders_and_agrees",
        False,
        LEGACY,
    ),
    (
        "the default contact language flips to English",
        'DEFAULT_CONTACT_LANGUAGE = "is"',
        'DEFAULT_CONTACT_LANGUAGE = "en"',
        "test_the_default_contact_language_is_unchanged_from_before_the_fix",
        True,
        IMPL,
    ),
    (
        # Headers move but the VALUES keep coming from role_is — Icelandic data
        # under English labels. This is why the English test asserts on values,
        # not only on headers.
        "--lang en changes the headers but still reads role_is",
        '    "en": (["Role", "Name"], "role", lambda v: v.title()),',
        '    "en": (["Role", "Name"], "role_is", lambda v: v.title()),',
        "test_english_contact_language",
        True,
        IMPL,
    ),
    (
        "an unknown language raises instead of falling back",
        "    headers, role_key, transform = CONTACT_TABLE_LANGUAGES.get(\n"
        "        language or DEFAULT_CONTACT_LANGUAGE,\n"
        "        CONTACT_TABLE_LANGUAGES[DEFAULT_CONTACT_LANGUAGE],\n"
        "    )",
        "    headers, role_key, transform = CONTACT_TABLE_LANGUAGES[\n"
        "        language or DEFAULT_CONTACT_LANGUAGE\n"
        "    ]",
        "test_an_unknown_language_falls_back_rather_than_raising",
        False,
        IMPL,
    ),
    (
        "a published value changes (byte-lock)",
        '    device_list = ["gnss_receiver", "antenna", "monument", "radome"]',
        '    device_list = ["gnss_receiver", "antenna", "monument", "dome"]',
        "test_working_implementation_matches_snapshot",
        False,
        IMPL,
    ),
    (
        # The structural floor. Re-snapshotted, so the byte-compare passes and
        # ONLY `_assert_rendered` can fail — reproducing "somebody accepted a
        # truncated render". The live crash emitted ~1,270 chars before
        # raising, which is why "non-empty" is not the assertion.
        #
        # The obvious mutation here is a TRAP: `device_list = [] or [...]`
        # reads like an emptying but `[] or X` evaluates to X, so it is a
        # no-op. It applied cleanly, changed the file, and reported the guard
        # as NOT DETECTED — a healthy guard blamed for a broken mutation.
        # Drop the two subtypes the floor actually asserts on instead.
        "the receiver/antenna rows vanish from the device table",
        '    device_list = ["gnss_receiver", "antenna", "monument", "radome"]',
        '    device_list = ["monument", "radome"]',
        "test_working_implementation_matches_snapshot",
        True,
        IMPL,
    ),
]


def _refuse_if_pytest_is_running():
    me = os.getpid()
    try:
        pids = subprocess.run(
            ["pgrep", "-f", r"python.* -m pytest"], capture_output=True, text=True
        ).stdout.split()
    except OSError:
        return
    others = []
    for pid in pids:
        if int(pid) == me:
            continue
        try:
            if os.readlink(f"/proc/{pid}/cwd") != str(REPO):
                continue
            argv = pathlib.Path(f"/proc/{pid}/cmdline").read_text().split(chr(0))
            if "python" not in pathlib.Path(argv[0]).name:
                continue
            others.append(f"{pid} {' '.join(argv)[:110]}")
        except OSError:
            continue
    if others:
        print("REFUSING: a pytest run is already using this working tree:")
        for ln in others[:3]:
            print("   ", ln[:120])
        print("This harness rewrites src/ in a loop; concurrent runs corrupt both.")
        sys.exit(2)


_refuse_if_pytest_is_running()

ORIGINALS = {IMPL: IMPL.read_text(), LEGACY: LEGACY.read_text()}


def restore():
    for path, text in ORIGINALS.items():
        path.write_text(text)
    if SNAPSHOT_BACKUP.exists():
        shutil.rmtree(SNAPSHOTS, ignore_errors=True)
        shutil.copytree(SNAPSHOT_BACKUP, SNAPSHOTS)


def pytest_k(selector, update=False):
    args = [str(PYTHON), "-m", "pytest", ORACLE, "-p", "no_network_plugin", "-q", "--no-header"]
    if selector:
        args += ["-k", selector]
    env = {
        "PYTHONPATH": PP,
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/home/bgo"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if update:
        env["STATION_HISTORY_ORACLE_UPDATE"] = "1"
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True, env=env)
    last = r.stdout.strip().splitlines()[-1] if r.stdout else ""
    if r.returncode == 5:
        return "NO_TESTS", last
    return r.returncode, last


def apply_mutation(old, new, path):
    s = path.read_text()
    hits = s.count("\n" + old)
    if hits != 1:
        print(f"       ({'ambiguous' if hits else 'absent'}: {hits} line-anchored matches)")
        return False
    path.write_text(s.replace("\n" + old, "\n" + new, 1))
    return True


shutil.rmtree(SNAPSHOT_BACKUP, ignore_errors=True)
shutil.copytree(SNAPSHOTS, SNAPSHOT_BACKUP)

bad = []
try:
    for name, old, new, selector, resnapshot, target in MUTATIONS:
        restore()
        if not apply_mutation(old, new, target):
            print(f"⚠️  {name}: ANCHOR NOT FOUND — mutation never applied")
            bad.append(name)
            continue
        if resnapshot:
            rc_up, _ = pytest_k("", update=True)
            if rc_up not in (0, 1):
                print(f"⚠️  {name}: re-snapshot run errored (rc={rc_up})")
                bad.append(name)
                continue
        rc, last = pytest_k(selector)
        if rc == "NO_TESTS":
            verdict = "⚠️  NO TESTS MATCHED"
            bad.append(name)
        else:
            verdict = "DETECTED" if rc != 0 else "❌ NOT DETECTED"
            if rc == 0:
                bad.append(name)
        tag = " [re-snapshotted]" if resnapshot else ""
        print(f"{verdict:16} {name}{tag}\n{'':17}{last}")
finally:
    restore()
    shutil.rmtree(SNAPSHOT_BACKUP, ignore_errors=True)

rc, last = pytest_k("")
print(f"\nrestored tree: {last}")
if rc != 0:
    print("RESTORE FAILED — the tree is not back to its original state.")
    sys.exit(2)
if bad:
    print("\nMutations that survived (their tests prove nothing):")
    for b in bad:
        print("  -", b)
    sys.exit(1)
print("\nEvery mutation was detected.")
