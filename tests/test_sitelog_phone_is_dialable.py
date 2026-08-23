"""IGS site-log phone numbers must be dialable from outside Iceland.

TOS stores Icelandic numbers bare ("5226000"). A site log is read worldwide, so
§11-§13 need the country code. §11 got this right by hardcoding "+354 " into its
f-string; **§12 did not**, and published the bare number whenever the responsible
agency differed from the point of contact — the branch at
`legacy/gps_metadata_functions.py` "12. Responsible Agency".

Scope when found (2026-08-23), measured against `~/git/gps-sitelogs`: 7 published
logs across 5 stations (eldc, eley, isak, nyla, rhof) carry a bare number, and
all 7 are in **§11 via the agencies path** — i.e. the separate
`gps-config-data/agencies.yaml` defect, since corrected to "+354 5226000". Zero
published logs carry the §12 defect this module guards, so the fix is defensive
rather than an incident.

The agencies path is deliberately NOT normalized: that yaml owns its own
formatting (its comment makes the country code REQUIRED in the value) and can
carry non-Icelandic agencies, where defaulting to +354 would be wrong.
"""

from __future__ import annotations

import logging

import pytest

from tostools.legacy.gps_metadata_functions import dialable_tos_phone, site_log

STATION = {
    "name": "Prófstöð",
    "marker": "TEST",
    "iers_domes_number": "12345M001",
    "lat": 64.13,
    "lon": -21.94,
    "altitude": 78.8,
    "date_start": "2020-01-01 00:00",
    "geological_characteristic": "bedrock",
    "bedrock_type": "igneous",
    "is_near_fault_zones": "NEI",
    "country": "Ísland",
    "tectonic_plate": "EURASIAN",
}


def _contact(id_entity: int, name: str, phone: str = "5226000") -> dict:
    """The shape `gpsqc.get_contacts` returns — bare phone, as TOS stores it."""
    return {
        "id_entity": id_entity,
        "role": "owner",
        "role_is": "Eigandi stöðvar",
        "name": name,
        "address": "Bústaðarvegur 7-9",
        "comment": "",
        "phone_primary": phone,
        "abbreviation": "IMO",
        "name_en": name,
        "email": "gnss-epos@vedur.is",
        "primary_contact": "GNSS Operator",
        "department": "Infrastructure",
        "address_en": "Bustadavegur 7-9",
        "main_url": "",
        "main_url_en": "",
    }


def _render(*, operator_differs: bool, phone: str = "5226000") -> str:
    """Render via the TOS-contact path (`agencies=None`).

    Reached in production whenever `resolve_sitelog_agencies` yields nothing —
    which needs no exception, since receivers' `sitelogs.py` passes its result
    straight through to the renderer.
    """
    operator = _contact(2 if operator_differs else 1, "National Land Survey", phone)
    station = dict(STATION)
    station["contact"] = {
        "contact": _contact(1, "Icelandic Meteorological Office", phone),
        "operator": operator,
        "owner": operator,
    }
    return site_log(
        "TEST",
        loglevel=logging.CRITICAL,
        station=station,
        device_sessions=[],
        agencies=None,
    )


def _phones(log: str) -> dict[str, str]:
    """Map section number -> its non-empty primary telephone value."""
    out, section = {}, None
    for line in log.splitlines():
        stripped = line.strip()
        if stripped[:3] in ("11.", "12.", "13."):
            section = stripped[:3]
        if "Telephone (primary)" in line:
            value = line.split(":", 1)[1].strip()
            if value:
                out[section] = value
    return out


class TestPublishedPhonesCarryTheCountryCode:
    def test_section_11_is_dialable(self):
        assert _phones(_render(operator_differs=False))["11."] == "+354 5226000"

    def test_section_12_is_dialable_when_the_agency_differs(self):
        """The regression. Before the fix this rendered a bare "5226000"."""
        assert _phones(_render(operator_differs=True))["12."] == "+354 5226000"

    def test_no_published_section_carries_a_bare_icelandic_number(self):
        for differs in (True, False):
            for section, value in _phones(_render(operator_differs=differs)).items():
                assert value.startswith("+"), f"§{section} not dialable: {value!r}"


class TestNormalizerIsIdempotent:
    """§11 previously hardcoded the prefix, so an already-prefixed TOS value
    would have rendered "+354 +354 5226000". Latent — TOS stores bare numbers —
    but a shared helper should not preserve the hazard."""

    def test_already_prefixed_is_left_alone(self):
        assert dialable_tos_phone("+354 5226000") == "+354 5226000"

    def test_applying_twice_changes_nothing(self):
        once = dialable_tos_phone("5226000")
        assert dialable_tos_phone(once) == once

    def test_a_foreign_number_is_not_given_an_icelandic_code(self):
        assert dialable_tos_phone("+45 12345678") == "+45 12345678"

    @pytest.mark.parametrize("empty", ["", None, "   "])
    def test_empty_stays_empty(self, empty):
        """A blank field is the site log's convention for unknown — never a
        bare "+354"."""
        assert dialable_tos_phone(empty) == ""

    def test_rendering_an_already_prefixed_contact_does_not_double_it(self):
        assert _phones(_render(operator_differs=True, phone="+354 5226000")) == {
            "11.": "+354 5226000",
            "12.": "+354 5226000",
        }


class TestAgenciesPathIsNotNormalized:
    """agencies.yaml owns its own formatting — it may carry non-Icelandic
    numbers, so the renderer must pass its value through verbatim rather than
    defaulting a country code onto it."""

    def test_agency_phone_is_rendered_verbatim(self):
        agencies = {
            "poc": {
                "name_lines": ["Norwegian Mapping Authority"],
                "abbrev": "NMA",
                "address": ["Hønefoss"],
                "contact_name": "Geodesy",
                "phone": "+47 32118100",
                "email": "post@kartverket.no",
            },
            "responsible": {
                "name_lines": ["NMA"],
                "abbrev": "NMA",
                "address": [],
                "contact_name": "",
                "phone": "",
                "email": "",
            },
            "data_center": {"primary": "NMA", "secondary": "", "url": ""},
        }
        log = site_log(
            "TEST",
            loglevel=logging.CRITICAL,
            station=dict(STATION),
            device_sessions=[],
            agencies=agencies,
        )
        assert "+47 32118100" in log
        assert "+354 +47" not in log
        assert "+354 32118100" not in log
