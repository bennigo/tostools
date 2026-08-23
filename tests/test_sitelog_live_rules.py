"""Two published-output rules, pinned against the renderer that ACTUALLY RUNS.

Both rules used to be tested only against ``core.site_log``'s section
helpers — a parallel renderer with no production caller, deleted 2026-08-23.
Those tests were green while the live path went unchecked, which is the
mechanism behind the VMEY M3G HTTP 422: a fix applied to the pretty module
shipped nothing.

So these drive :func:`tostools.core.site_log.build_site_log` — the single
entry point behind ``tosGPS sitelog`` and receivers' M3G dissemination —
end to end against a recorded TOS interaction, and assert on the rendered
site-log text. No hand-built ``device_sessions`` fixture: the cassette
carries the real payload, so the test cannot pass on a shape production
never produces.

Re-record with::

    pytest tests/test_sitelog_live_rules.py --record-mode=once

Fixture stations are chosen because they genuinely exercise the rules:

- **ISAK** carries a synthetic antenna serial (``antenna-ISAK-19920731``) in
  TOS, and its 2026-08-04 site log published that value verbatim — the exact
  class of value M3G rejects.
- **VMEY** is the station of the 422 itself, and carries a monument height
  and an antenna eccentricity that are separate, non-zero, and differ.
"""

from __future__ import annotations

import logging
import re

import pytest

from tostools.core.site_log import build_site_log
from tostools.device import PUBLISHED_UNKNOWN_ANTENNA_SERIAL

#: §4 antenna blocks: "     Serial Number            : <value>"
_SERIAL_RE = re.compile(r"^\s*Serial Number\s*:\s*(.*?)\s*$", re.MULTILINE)
#: §4 "     Marker->ARP Up Ecc. (m) : 0.0000"
_UP_ECC_RE = re.compile(r"Marker->ARP Up Ecc.*?:\s*([0-9.+-]+)", re.IGNORECASE)


#: Unfilled IGS template hints — "(A20, but note the first A5 …)" — and lines
#: where a second "label : value" pair shares the row. Neither is a serial, and
#: leaving them in would let a genuinely blank serial hide in the noise.
def _is_template_noise(value: str) -> bool:
    return value.startswith("(") or " : " in value


def _antenna_serials(log: str) -> list:
    """Real Serial Number values in the rendered log, template hints removed."""
    return [
        m.group(1)
        for m in _SERIAL_RE.finditer(log)
        if not _is_template_noise(m.group(1))
    ]


@pytest.mark.vcr
def test_a_synthetic_antenna_serial_never_reaches_the_published_log():
    """The rule the VMEY HTTP 422 was about, on the path that publishes.

    A synthetic ``<subtype>-<STID>-<YYYYMMDD>`` key must render as ``0000``,
    never verbatim and never blank: only the first 5 characters reach SINEX,
    so ``antenna-isak-19920731`` would be distributed worldwide as ``anten``,
    and M3G rejects an EMPTY serial with 422 "check the Antenna section".
    """
    log = build_site_log("ISAK", loglevel=logging.CRITICAL)
    assert log, "renderer produced nothing — re-record the cassette"

    assert "antenna-" not in log.lower(), (
        "a synthetic antenna key reached the rendered site log; this is what "
        "isak00isl_20260804.log published verbatim"
    )
    serials = _antenna_serials(log)
    assert serials, "no Serial Number lines found — did §3/§4 render?"
    assert PUBLISHED_UNKNOWN_ANTENNA_SERIAL in serials, (
        f"expected the {PUBLISHED_UNKNOWN_ANTENNA_SERIAL!r} placeholder for "
        f"ISAK's synthetic antenna serial; got {serials}"
    )


@pytest.mark.vcr
def test_no_antenna_serial_is_published_blank():
    """M3G 422s an empty serial — proven by bisection on VMEY 2026-08-20."""
    log = build_site_log("ISAK", loglevel=logging.CRITICAL)
    assert log, "renderer produced nothing — re-record the cassette"
    assert "" not in _antenna_serials(log), (
        "an antenna Serial Number rendered blank; M3G answers 422 "
        "'check the Antenna section' for that"
    )


@pytest.mark.vcr
def test_up_ecc_is_the_monument_plus_eccentricity_composite():
    """§4 "Marker->ARP Up Ecc." must equal the RINEX ``ANTENNA: DELTA H``.

    TOS stores the antenna eccentricity (monument-top → ARP) separately from
    the monument height (mark → monument-top), in *different* device-history
    sessions. The published value is their sum — the same composite the
    RINEX-header path computes — not the bare antenna ARP.
    """
    log = build_site_log("VMEY", loglevel=logging.CRITICAL)
    assert log, "renderer produced nothing — re-record the cassette"

    values = [float(v) for v in _UP_ECC_RE.findall(log)]
    assert values, "no Marker->ARP Up Ecc. line found — did §4 render?"
    # VMEY's monument is ~1 m, so every composite is ~0.999–1.069. A bare
    # antenna ARP delta is ~0.0–0.15 m, so a 0.5 floor separates "monument
    # height reached the sum" from "the lookup returned nothing and we
    # published the eccentricity alone" — the failure this pins. EVERY value
    # is checked, not just one: a single missed period is the realistic bug.
    assert all(v > 0.5 for v in values), (
        f"an Up Ecc. is too small to include the monument height {values} — "
        "the composite lost its monument term (see the ARP-vs-station.info "
        "trap: the antenna entity holds the delta ABOVE the monument, not the "
        "mark-to-ARP total)"
    )
