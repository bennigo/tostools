#!/usr/bin/env python3
"""Mutation-test the site-log oracle.

    python3 scripts/dev/mutate_sitelog_oracle.py

Run it after ANY change to the live renderer
(`src/tostools/legacy/gps_metadata_functions.py::site_log`), to
`core/site_log.py`, or to `tests/test_sitelog_oracle.py` itself. Exits
non-zero and names the survivors.

Break one guard at a time, assert the test claiming to cover it goes RED.
A mutation that leaves the suite green means the test proves nothing.

The re-snapshot mode is the point of this harness
-------------------------------------------------
A snapshot oracle has a specific way of proving nothing, and it is not the
one a plain mutation run catches. Every mutation to the renderer changes the
rendered bytes, so `test_site_log_matches_snapshot` goes red for ALL of them
— including mutations that gut §3 entirely. That makes the structural
assertions in `_assert_publishable` look covered when they are dead weight
riding on the byte-compare.

The failure they actually exist for is: someone re-snapshots from a broken
state (`SITELOG_ORACLE_UPDATE=1` after a bad refactor), the byte-compare
goes green against the garbage, and the garbage ships to M3G.

So mutations marked `resnapshot=True` are run the way that failure happens:
mutate, regenerate the snapshots from the MUTATED renderer, and only then
run the test. The byte-compare is now satisfied by construction. If the test
is still red, the structural guard is real. If it goes green, the guard is
decoration and the oracle would have blessed a broken publish.

Traps inherited from `receivers/scripts/dev/mutate_reconcile.py`, both of
which have produced a confident wrong answer in this codebase:

* **Stale bytecode.** Two mutations of equal length within the same second
  yield a `.pyc` that mtime+size invalidation accepts, so the second run
  imports the first mutation's bytecode. Hence PYTHONDONTWRITEBYTECODE=1.
* **Ambiguous anchors.** Anchors are line-anchored and must match EXACTLY
  once; a substring match silently mutates the wrong code while still
  changing the file, so "did it apply?" says yes and a healthy guard is
  reported undetected.

Anchors are literal source text and WILL rot as the code moves. A rotted
anchor reports "ANCHOR NOT FOUND" and fails the run rather than passing
silently — fix the anchor, never delete the mutation.
"""

import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
RENDER = REPO / "src/tostools/legacy/gps_metadata_functions.py"
ORACLE = "tests/test_sitelog_oracle.py"
SNAPSHOTS = REPO / "tests/_oracle_outputs/sitelog"

#: `no_network_plugin` lives in the receivers checkout — this suite is known
#: to reach the live TOS API wherever a cassette or mock detaches, and the
#: oracle must be proven to run entirely off its cassettes.
PP = str(REPO.parent / "receivers/scripts/dev")
PYTHON = sys.executable

# (name, old, new, -k selector, resnapshot)
MUTATIONS = [
    (
        "byte-lock: a published label changes",
        "            f\"     Elevation Cutoff Setting : {elevation_cuttoff}\\n\"",
        "            f\"     Elevation Cutoff Angle   : {elevation_cuttoff}\\n\"",
        "test_site_log_matches_snapshot",
        False,
    ),
    (
        # Two-line anchor: the `or "000000"` fallback line is IDENTICAL in the
        # §3 receiver and §4 antenna builders, so a one-line anchor matches
        # twice and the harness (correctly) refuses. The preceding
        # `satellite_system` line is unique to the receiver builder.
        "byte-lock: a published VALUE changes",
        "        satellite_system = satellite_system_from_toggles(device)\n"
        "        serial_number = device.get(\"serial_number\") or \"000000\"",
        "        satellite_system = satellite_system_from_toggles(device)\n"
        "        serial_number = device.get(\"serial_number\") or \"999999\"",
        "test_site_log_matches_snapshot",
        False,
    ),
    (
        "§0 Date Prepared is frozen, not stamped",
        "        f\"     Date Prepared            : {dt.now().strftime('%Y-%m-%d')}\\n\"",
        "        f\"     Date Prepared            : 2020-01-01\\n\"",
        "test_date_prepared_is_stamped_with_today",
        True,
    ),
    (
        "§3 collapses to the bare IGS template stub",
        "    for session_nr, session in enumerate(receiver_list):",
        "    for session_nr, session in enumerate([]):",
        "test_site_log_matches_snapshot",
        True,
    ),
    (
        "§4 collapses to the bare IGS template stub",
        "    for session_nr, session in enumerate(antenna_list):",
        "    for session_nr, session in enumerate([]):",
        "test_site_log_matches_snapshot",
        True,
    ),
    (
        "§3 block numbering starts at 2 (a session was dropped)",
        "            f\"{f'3.{session_nr + 1}':<5}Receiver Type            : {device_type}\\n\"",
        "            f\"{f'3.{session_nr + 2}':<5}Receiver Type            : {device_type}\\n\"",
        "test_site_log_matches_snapshot",
        True,
    ),
    (
        "a synthetic antenna serial reaches the published log",
        "            serial_number = PUBLISHED_UNKNOWN_ANTENNA_SERIAL",
        "            serial_number = serial_number",
        "test_site_log_matches_snapshot",
        True,
    ),
    (
        "a required IGS section disappears",
        "        \"5.   Surveyed Local Ties\\n\"",
        "        \"5x.  Surveyed Local Ties\\n\"",
        "test_site_log_matches_snapshot",
        True,
    ),
    (
        "the scrub widens into a blanket date filter",
        None,  # mutates the TEST, not the renderer
        None,
        "test_scrub_only_touches_the_generation_date",
        False,
    ),
]


def _refuse_if_pytest_is_running():
    """This harness REWRITES source files in a loop. Anything else importing
    them at the same time reads a file that is changing underneath it.

    Not theoretical — in the receivers tree this collision produced four
    spurious failures in tests using `inspect.getsource`, because line
    offsets shifted mid-run.
    """
    me = os.getpid()
    try:
        pids = subprocess.run(
            ["pgrep", "-f", r"python.* -m pytest"],
            capture_output=True,
            text=True,
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

ORIGINAL_SRC = RENDER.read_text()
ORIGINAL_TEST = (REPO / ORACLE).read_text()
SNAPSHOT_BACKUP = REPO / "tests/_oracle_outputs/.sitelog_backup"


def restore():
    RENDER.write_text(ORIGINAL_SRC)
    (REPO / ORACLE).write_text(ORIGINAL_TEST)
    if SNAPSHOT_BACKUP.exists():
        shutil.rmtree(SNAPSHOTS, ignore_errors=True)
        shutil.copytree(SNAPSHOT_BACKUP, SNAPSHOTS)


def _env(**extra):
    env = {
        "PYTHONPATH": PP,
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/home/bgo"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(extra)
    return env


def pytest_k(selector, update=False):
    args = [
        str(PYTHON),
        "-m",
        "pytest",
        ORACLE,
        "-p",
        "no_network_plugin",
        "-q",
        "--no-header",
    ]
    if selector:
        args += ["-k", selector]
    r = subprocess.run(
        args,
        cwd=REPO,
        capture_output=True,
        text=True,
        env=_env(**({"SITELOG_ORACLE_UPDATE": "1"} if update else {})),
    )
    last = r.stdout.strip().splitlines()[-1] if r.stdout else ""
    if r.returncode == 5:
        # pytest exit 5 = nothing collected. Non-zero reads as "DETECTED", so
        # a selector matching nothing would silently certify an untested
        # mutation. Surface it as a harness error instead.
        return "NO_TESTS", last
    return r.returncode, last


def apply_mutation(old, new, path=RENDER):
    """Return True only if the mutation was really applied, exactly once."""
    s = path.read_text()
    hits = s.count("\n" + old)
    if hits != 1:
        print(f"       ({'ambiguous' if hits else 'absent'}: {hits} line-anchored matches)")
        return False
    path.write_text(s.replace("\n" + old, "\n" + new, 1))
    return True


# Snapshot the pristine snapshots so a re-snapshot mutation can be undone.
shutil.rmtree(SNAPSHOT_BACKUP, ignore_errors=True)
shutil.copytree(SNAPSHOTS, SNAPSHOT_BACKUP)

bad = []
try:
    for name, old, new, selector, resnapshot in MUTATIONS:
        restore()
        if old is None:
            # The scrub-widening mutation targets the TEST's own regex: a
            # blanket `\d{4}-\d{2}-\d{2}` filter would scrub the TOS install
            # dates too, silently un-guarding the era boundaries.
            applied = apply_mutation(
                '    r"^(?P<head>\\s*Date Prepared\\s*:\\s*)(?P<date>\\d{4}-\\d{2}-\\d{2})\\s*$",',
                '    r"(?P<head>)(?P<date>\\d{4}-\\d{2}-\\d{2})",',
                REPO / ORACLE,
            )
        else:
            applied = apply_mutation(old, new)
        if not applied:
            print(f"⚠️  {name}: ANCHOR NOT FOUND — mutation never applied")
            bad.append(name)
            continue

        if resnapshot:
            # Regenerate snapshots FROM THE MUTATED RENDERER, so the
            # byte-compare is satisfied by construction and only the
            # structural guards can still fail. This is the mode that
            # reproduces "somebody re-snapshotted a broken state".
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
