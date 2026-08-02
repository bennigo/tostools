"""Recover the recorded constellation set from raw SBF when RINEX can't say.

This is the "raw decode" ground-truth tier that :mod:`tostools.constellation`
lists as a follow-up. It exists because **RINEX 2 cannot express the answer**:
its header carries no per-system list, so an R2 reading is a lower bound and
its *absence* of Galileo/BeiDou proves nothing. The IMO archive is R2 until
2026, which means the entire 2017-2025 history of every station is unreadable
from RINEX headers alone.

The SBF is not: it records every system the receiver actually tracked,
whatever RINEX was later derived from it. Converting one SBF to RINEX 3 in a
temp directory and reading its ``SYS / # / OBS TYPES`` lines recovers the true
set — measured at **0.5-0.8 s** per file, and the archive keeps the raw
alongside the RINEX.

Why this beats re-rinexing the archive first
--------------------------------------------
Answering "when did this constellation switch on" needs *transition dates*, not
every file. A binary search over a decade is ~12 probes ≈ 8 seconds per
receiver period; re-rinexing ISAK alone is 6,312 files. Re-rinexing to R3 is
worth doing for its own reasons (better headers, modern format) but making it a
prerequisite would turn a 12-file question into a million-file migration, and
the TOS dates would stay wrong until it finished. Proven on ISAK 2026-08-02:
2018 → ``[GR]``, 2021 → ``[GR]``, 2024 → ``[EGR]``, i.e. Galileo arrived
between 2021 and 2024 — three files, under two seconds.

Degrades gracefully: with no ``sbf2rin`` on PATH, or no raw archived for a
date, the caller keeps the original (unreliable) RINEX reading rather than
failing. The audit therefore behaves exactly as before on a host without the
binary.
"""

from __future__ import annotations

import gzip
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union

from .archive import classify_file_format
from .constellation import (
    ConstellationReading,
    read_constellations,
    systems_from_header,
)

logger = logging.getLogger(__name__)

#: Converter that turns Septentrio SBF into RINEX. Part of the RxTools/gps-tools
#: toolchain, present on the production host and dev boxes.
SBF2RIN = "sbf2rin"

#: Per-file conversion budget. Measured 0.5-0.8 s for a 5-9 MB daily SBF; the
#: ceiling exists so one pathological file cannot stall a fleet sweep.
CONVERT_TIMEOUT_S = 180

#: Raw extensions understood here, in the order we try them.
_RAW_SUFFIXES = (".sbf.gz", ".sbf")


def sbf2rin_available(exe: str = SBF2RIN) -> bool:
    """True when the SBF converter can be found on PATH."""
    return shutil.which(exe) is not None


def raw_for_rinex(rinex_path: Union[str, Path]) -> Optional[Path]:
    """Locate the raw SBF recorded on the same day as ``rinex_path``.

    Resolves against the RINEX file's own ``raw/`` sibling rather than an
    archive root, which is deliberate: the IMO archive is split across a recent
    root (``/mnt/data/gpsdata``) and a historical one (``/mnt/rawgpsdata``), and
    deriving the sibling means whichever root the RINEX came from is the one we
    look in. Returns ``None`` when the day has no raw archived.
    """
    rinex_path = Path(rinex_path)
    raw_dir = rinex_path.parent.parent / "raw"
    if not raw_dir.is_dir():
        return None

    fmt = classify_file_format(rinex_path.name)
    day = getattr(fmt, "date", None)
    if day is None:
        return None

    # Raw naming is <MARKER><YYYYMMDD><HHMM><session>.sbf.gz — match on the
    # marker+date prefix and take the earliest of the day (daily sessions have
    # one; hourly sessions would give the 0000 file, which is what we want).
    marker = rinex_path.name[:4].upper()
    prefix = f"{marker}{day:%Y%m%d}"
    candidates = sorted(
        p
        for p in raw_dir.iterdir()
        if p.is_file()
        and p.name.upper().startswith(prefix)
        and p.name.endswith(_RAW_SUFFIXES)
    )
    return candidates[0] if candidates else None


def systems_from_sbf(
    sbf_path: Union[str, Path],
    *,
    exe: str = SBF2RIN,
    timeout_s: int = CONVERT_TIMEOUT_S,
) -> Optional[ConstellationReading]:
    """Convert one SBF to RINEX 3 in a temp dir and read its constellation set.

    The archive is never touched: the raw is copied (and decompressed) into a
    ``TemporaryDirectory`` that is removed on exit, so a failed or interrupted
    conversion cannot strand intermediates next to the data — the failure mode
    that has bitten the Trimble converter.

    Returns ``None`` (never raises) when the converter is missing, the run
    fails or times out, or the output has no readable header; the caller then
    keeps whatever the RINEX header gave it.
    """
    resolved = shutil.which(exe)
    if resolved is None:
        logger.debug("%s not on PATH — no SBF fallback", exe)
        return None

    sbf_path = Path(sbf_path)
    try:
        with tempfile.TemporaryDirectory(prefix="tos_sbf_") as td:
            work_dir = Path(td)
            local = work_dir / sbf_path.name

            if sbf_path.name.endswith(".gz"):
                local = work_dir / sbf_path.name[: -len(".gz")]
                with gzip.open(sbf_path, "rb") as src, local.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            else:
                shutil.copyfile(sbf_path, local)

            out = work_dir / "out.rnx"
            proc = subprocess.run(
                [resolved, "-f", str(local), "-R3", "-o", out.name],
                cwd=str(work_dir),
                capture_output=True,
                timeout=timeout_s,
            )
            if not out.is_file() or out.stat().st_size == 0:
                logger.debug(
                    "sbf2rin produced no output for %s (rc=%s)",
                    sbf_path.name,
                    proc.returncode,
                )
                return None

            # Header only — stop at END OF HEADER rather than reading a
            # multi-MB observation body we have no use for.
            lines = []
            with out.open("r", errors="replace") as fh:
                for line in fh:
                    lines.append(line)
                    if "END OF HEADER" in line:
                        break

            reading = systems_from_header("".join(lines))
            if not reading.systems:
                return None
            return ConstellationReading(
                version=reading.version,
                systems=reading.systems,
                reliable=reading.reliable,
                source_path=str(sbf_path),
            )
    except (subprocess.TimeoutExpired, OSError, EOFError, gzip.BadGzipFile) as exc:
        logger.debug("SBF decode failed for %s: %s", sbf_path, exc)
        return None


def read_constellations_sbf_first(
    path: Union[str, Path],
) -> Optional[ConstellationReading]:
    """RINEX header, falling back to raw SBF when the header is unreliable.

    Drop-in for :func:`tostools.constellation.read_constellations` — same
    signature, so it can be passed straight to
    ``segment_by_constellation(files, read_fn=...)``.

    A RINEX-3 header is already authoritative and is returned untouched; the
    decode only runs for R2 (or unparseable) headers, which is precisely the
    2017-2025 span the archive cannot otherwise answer for.
    """
    reading = read_constellations(path)
    if reading is not None and reading.reliable:
        return reading

    raw = raw_for_rinex(path)
    if raw is None:
        return reading

    decoded = systems_from_sbf(raw)
    if decoded is None:
        return reading

    logger.debug("SBF fallback for %s → %s", Path(path).name, sorted(decoded.systems))
    return decoded
