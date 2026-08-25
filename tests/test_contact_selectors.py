"""Tests for the `contact.*` selector kind + --owner/--no-owner flag.

Covers the fourth selector namespace: role-scoped owner/operator/
data_owner orgs plus the any-contact organization/name/email fields, with
existential positives and universal negation.
"""

from __future__ import annotations

import pytest

from tostools.search import (
    CONTACT_NAMESPACE,
    contacts_satisfy,
    parse_expression,
    parse_selector,
)


def _c(role_is="Eigandi stöðvar", organization="Veðurstofa Íslands", name="", email=""):
    return {
        "role_is": role_is,
        "organization": organization,
        "name": name,
        "email": email,
    }


# ── parsing ────────────────────────────────────────────────────────────────


def test_parse_selector_accepts_contact_namespace():
    assert parse_selector("contact.owner") == (CONTACT_NAMESPACE, "owner")
    assert parse_selector("contact.organization") == (CONTACT_NAMESPACE, "organization")


def test_parse_selector_rejects_unknown_contact_field():
    with pytest.raises(ValueError, match="unknown contact field"):
        parse_selector("contact.bogus")


# ── contacts_satisfy ───────────────────────────────────────────────────────


def test_owner_org_matches_role_scoped():
    contacts = [_c(organization="Jarðvísindastofnun Háskóla Íslands")]
    assert contacts_satisfy(contacts, [parse_expression("contact.owner ~ Háskóla")])


def test_owner_negation_is_universal():
    contacts = [_c(organization="Jarðvísindastofnun Háskóla Íslands")]
    assert not contacts_satisfy(
        contacts, [parse_expression("contact.owner !~ Háskóla")]
    )
    contacts = [_c(organization="Veðurstofa Íslands")]
    assert contacts_satisfy(contacts, [parse_expression("contact.owner !~ Háskóla")])


def test_role_scoping_excludes_other_roles():
    # The owner is IMO but the OPERATOR is IES — contact.owner must not match IES.
    contacts = [
        _c(role_is="Eigandi stöðvar", organization="Veðurstofa Íslands"),
        _c(role_is="Rekstraraðili", organization="Jarðvísindastofnun Háskóla Íslands"),
    ]
    assert not contacts_satisfy(contacts, [parse_expression("contact.owner ~ Háskóla")])
    assert contacts_satisfy(contacts, [parse_expression("contact.operator ~ Háskóla")])
    # any-contact organization spans both roles.
    assert contacts_satisfy(
        contacts, [parse_expression("contact.organization ~ Háskóla")]
    )


def test_data_owner_role():
    contacts = [_c(role_is="Eigandi gagna", organization="Náttúrufræðistofnun Íslands")]
    assert contacts_satisfy(
        contacts, [parse_expression("contact.data_owner ~ Náttúrufræði")]
    )
    assert not contacts_satisfy(
        contacts, [parse_expression("contact.owner ~ Náttúrufræði")]
    )


def test_owner_null_is_absence():
    assert contacts_satisfy([], [parse_expression("contact.owner = null")])
    assert not contacts_satisfy([_c()], [parse_expression("contact.owner = null")])
    assert contacts_satisfy([_c()], [parse_expression("contact.owner != null")])


def test_owner_reads_organization_fallback_name():
    # Some contacts carry the org only in `name`.
    contacts = [
        {
            "role_is": "Eigandi stöðvar",
            "organization": "",
            "name": "Jarðvísindastofnun Háskóla Íslands",
        }
    ]
    assert contacts_satisfy(contacts, [parse_expression("contact.owner ~ Háskóla")])


def test_email_field_matches_any_contact():
    contacts = [_c(email="gnss@vedur.is")]
    assert contacts_satisfy(contacts, [parse_expression("contact.email ~ vedur.is")])


def test_contact_is_a_discoverable_selectors_topic():
    from tostools import search_selectors as sel

    assert sel.resolve_topic("contact") == sel.TOPIC_CONTACT
    group = sel.contact_group()
    selectors = [e.selector for e in group.entries]
    assert selectors == [
        "contact.owner",
        "contact.operator",
        "contact.data_owner",
        "contact.organization",
        "contact.name",
        "contact.email",
    ]


def test_org_term_expands_abbreviation(monkeypatch):
    from tostools import search as sm

    monkeypatch.setattr(
        sm,
        "_org_aliases",
        lambda: {
            "ies": "Jarðvísindastofnun Háskóla Íslands",
            "jhí": "Jarðvísindastofnun Háskóla Íslands",
        },
    )
    assert sm._expand_org_term("IES") == "Jarðvísindastofnun Háskóla Íslands"
    assert sm._expand_org_term("jhí") == "Jarðvísindastofnun Háskóla Íslands"
    # a plain substring passes through untouched
    assert sm._expand_org_term("Háskóla") == "Háskóla"


def test_owner_selector_accepts_abbreviation(monkeypatch):
    from tostools import search as sm

    monkeypatch.setattr(
        sm,
        "_org_aliases",
        lambda: {"ies": "Jarðvísindastofnun Háskóla Íslands"},
    )
    contacts = [_c(organization="Jarðvísindastofnun Háskóla Íslands")]
    assert contacts_satisfy(contacts, [parse_expression("contact.owner ~ IES")])
    assert not contacts_satisfy(contacts, [parse_expression("contact.owner !~ IES")])
