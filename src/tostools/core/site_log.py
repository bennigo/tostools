"""
IGS Site Log generation and management.

This module provides functions for generating IGS-standard site logs from TOS
metadata.

Everything here supports the ONE site-log path:
:func:`build_site_log` (the shared entry point for ``tosGPS sitelog`` and
receivers' M3G dissemination), the §0 dated-series helper
:func:`find_previous_site_log`, the filename builder
:func:`generate_igs_sitelog_filename`, and the writer
:func:`export_site_log_to_file`.

``generate_igs_site_log`` and its nine private section helpers were DELETED
on 2026-08-23. They were a complete parallel renderer with no production
caller — only their own tests and a commented-out import — while two
docstrings named them as canonical. That is how the VMEY HTTP 422 happened:
a fix applied to the pretty module shipped nothing. The renderer that runs
is ``legacy.gps_metadata_functions.site_log``, reached through
:func:`build_site_log`.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from ..utils.logging import get_logger


def export_site_log_to_file(
    site_log_content: str,
    output_path: str,
    marker: str,
    loglevel: int = logging.WARNING,
) -> bool:
    """
    Export site log content to file.

    Args:
        site_log_content: Generated site log content
        output_path: Output file path
        marker: Station marker for filename
        loglevel: Logging level

    Returns:
        True if successful, False otherwise
    """
    logger = get_logger(__name__, loglevel)

    try:
        # IGS site logs are ISO-8859-1 (Latin-1), not UTF-8 — that is what M3G
        # serves back (`file` reports "ISO-8859 text" on every log fetched from
        # gnss-metadata.eu) and what the IGS series has always used. Writing
        # UTF-8 made every Icelandic character a two-byte sequence that renders
        # as mojibake for anyone reading the published log, and made a local↔M3G
        # diff show spurious changes on every line containing á é í ó ú ý þ æ ö ð.
        #
        # Latin-1 covers Icelandic completely, so nothing is lost. Encoding is
        # STRICT on purpose: a character genuinely outside Latin-1 (a typographic
        # dash pasted into an address, say) raises here and is reported as an
        # export failure by the caller, rather than being silently replaced with
        # "?" in a document that gets distributed worldwide.
        with open(output_path, "w", encoding="latin-1") as f:
            f.write(site_log_content)

        logger.info(f"Site log exported to {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to export site log: {e}")
        return False


# ---------------------------------------------------------------------------
# The single site-log entry point
# ---------------------------------------------------------------------------


def build_site_log(
    station: str,
    *,
    client: Any = None,
    agencies: Optional[Dict[str, Any]] = None,
    previous_log: str = "",
    report_type: Optional[str] = None,
    modified_sections: str = "1",
    monument_number: str = "00",
    country_code: str = "ISL",
    loglevel: int = logging.WARNING,
) -> str:
    """Render a station's IGS site log — the ONE way to do it.

    Both callers go through here so they cannot drift:

    - ``tosGPS sitelog``
    - receivers' M3G dissemination (``epos-disseminate --sitelog``)

    They used to call the renderer directly with *different* argument sets,
    and agreed only because the omitted arguments happened to share defaults:
    receivers passed ``monument_number`` / ``country_code`` and never
    ``report_type``; tosGPS did the reverse. Byte-identical output today,
    silently divergent the first time a non-default reached one of them.

    ``report_type`` defaults to the M3G convention — ``NEW`` for the first log
    in a dated series, ``UPDATE`` once a previous one exists — rather than
    being each caller's own guess.

    ``agencies=None`` resolves §11/§12/§13 from TOS roles + agencies.yaml via
    :func:`tostools.core.agencies.resolve_sitelog_agencies`. Resolution is
    best-effort: on any failure the renderer falls back to its legacy
    TOS-contact rendering, which produces a *different* §11, so a warning is
    logged rather than the difference passing unnoticed.

    NOTE the renderer is ``legacy.gps_metadata_functions.site_log``, not
    :func:`generate_igs_site_log` above — see this module's docstring.
    """
    from ..legacy.gps_metadata_functions import site_log as _render

    sid = station.upper()

    if agencies is None:
        try:
            if client is None:
                from ..api.tos_client import TOSClient

                client = TOSClient()
            meta = client.get_complete_station_metadata(sid)
            if meta:
                from .agencies import resolve_sitelog_agencies

                agencies = resolve_sitelog_agencies(client, meta)
        except Exception as exc:  # noqa: BLE001 - enrichment, never fatal
            get_logger(__name__, loglevel).warning(
                "site log %s: agency resolution failed (%s) — falling back to "
                "the legacy TOS-contact rendering, which yields a different §11",
                sid,
                exc,
            )
            agencies = None

    if report_type is None:
        report_type = "UPDATE" if previous_log else "NEW"

    return _render(
        sid,
        loglevel=loglevel,
        report_type=report_type,
        previous_log=previous_log,
        modified_sections=modified_sections,
        agencies=agencies,
        monument_number=monument_number,
        country_code=country_code.upper(),
    )


def find_previous_site_log(out_dir: Any, nine_char: str, current_date: str) -> str:
    """The latest dated site log for ``nine_char`` older than ``current_date``.

    The M3G convention is a dated series (``rhof00isl_20240827.log``); §0
    "Previous Site Log" chains each log to its predecessor. Lexicographic sort
    == chronological for ``YYYYMMDD`` names.

    **``current_date``'s own file is excluded**, so a same-day regeneration
    does not chain a log to itself. That exclusion is the whole reason this
    is the surviving implementation: ``tosGPS`` carried its own
    ``find_previous_sitelog(station_dir, station_id)`` that globbed and took
    the last name with no date filter, so a second ``tosGPS sitelog
    --auto-filename`` run on the same day produced a log whose §0 pointed at
    itself. Unified here 2026-08-23.

    Empty string when no prior log exists (first log in the series).
    """
    from pathlib import Path as _Path

    prefix = nine_char.lower()
    current_name = f"{prefix}_{current_date}.log"
    try:
        names = sorted(
            p.name
            for p in _Path(out_dir).glob(f"{prefix}_*.log")
            if p.name < current_name
        )
    except OSError:
        return ""
    return names[-1] if names else ""


# Moved from tosGPS.py 2026-08-23. It is a library function that lived in a
# CLI module, which is why receivers had to `from tostools.tosGPS import
# generate_igs_sitelog_filename` — importing a CLI to get a helper. tosGPS
# re-exports it so that import keeps working.
def generate_igs_sitelog_filename(
    station_marker: str,
    country_code: str = "ISL",
    monument_number: str = "00",
    include_date: bool = False,
    base_dir: str = ".",
    custom_date: str = None,
    create_station_subdir: bool = True,
) -> tuple[str, str]:
    """
    Generate IGS-compliant site log filename and directory path.

    Format without date: {STATION}{MONUMENT}{COUNTRY}.log
    Format with date: {station}{monument}{country}_{YYYYMMDD}.log
    Example: RHOF00ISL.log or rhof00isl_20250825.log

    Args:
        station_marker: 4-character station code (e.g., "RHOF")
        country_code: 3-character country code (default: "ISL" for Iceland)
        monument_number: 2-digit monument number (default: "00" for main monument)
        include_date: Whether to include current date in filename
        base_dir: Base directory for site log storage
        create_station_subdir: Whether to create station-specific subdirectory (default: True)

    Returns:
        Tuple of (full_path, filename_only)
    """
    import os

    station_id = f"{station_marker.upper()}{monument_number}{country_code.upper()}"

    if create_station_subdir:
        output_dir = os.path.join(base_dir, station_id)
    else:
        output_dir = base_dir

    if include_date:
        if custom_date:
            date_str = custom_date  # Use provided date (YYYYMMDD format)
        else:
            date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{station_id.lower()}_{date_str}.log"
    else:
        filename = f"{station_id}.log"

    full_path = os.path.join(output_dir, filename)
    return full_path, filename
