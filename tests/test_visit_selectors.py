"""Tests for the `visit.*` selector kind in `tos search`.

Covers the third selector namespace: free-text visit fields
(work/comment/remaining/all), structured fields (type/participants),
same-visit AND for positives, universal negation for negatives, and the
quote-stripping ergonomic on `parse_expression`.
"""

from __future__ import annotations

import pytest

from tostools.search import (
    VISIT_NAMESPACE,
    parse_expression,
    parse_selector,
    visits_satisfy,
)


def _v(
    work=None, comment=None, remaining=None, vtype="remote", participants="bgo@vedur.is"
):
    return {
        "id": 1,
        "work": work,
        "comment": comment,
        "remaining": remaining,
        "maintenance_type": vtype,
        "participants": participants,
        "participants_names": "Benedikt Ófeigsson",
        "start_time": "2026-08-24T00:00:00",
    }


# ── selector parsing ────────────────────────────────────────────────────────


def test_parse_selector_accepts_visit_namespace():
    assert parse_selector("visit.work") == (VISIT_NAMESPACE, "work")
    assert parse_selector("visit.all") == (VISIT_NAMESPACE, "all")
    assert parse_selector("visit.type") == (VISIT_NAMESPACE, "type")


def test_parse_selector_rejects_unknown_visit_field():
    with pytest.raises(ValueError, match="unknown visit field"):
        parse_selector("visit.bogus")


def test_parse_expression_strips_surrounding_quotes():
    p = parse_expression('visit.work ~ "TOS reviewed"')
    assert p.value == "TOS reviewed"
    assert p.op == "~"
    assert p.namespace == VISIT_NAMESPACE


def test_parse_expression_preserves_lone_quote():
    p = parse_expression("visit.work ~ 'abc")
    assert p.value == "'abc"  # unmatched leading quote stays literal


# ── visits_satisfy semantics ────────────────────────────────────────────────


def test_positive_existential():
    visits = [_v(work="firmware uppfært"), _v(work="TOS reviewed, re-rinexed")]
    assert visits_satisfy(visits, [parse_expression('visit.work ~ "TOS reviewed"')])


def test_negation_is_universal():
    # One visit matches, so !~ must be FALSE (a matching visit exists).
    visits = [_v(work="TOS reviewed, re-rinexed")]
    assert not visits_satisfy(
        visits, [parse_expression('visit.work !~ "TOS reviewed"')]
    )
    # No matching visit → !~ holds (the "left to do" cross-check).
    visits = [_v(work="firmware uppfært")]
    assert visits_satisfy(visits, [parse_expression('visit.work !~ "TOS reviewed"')])


def test_visit_all_searches_any_note_field():
    # "TOS" lives in the comment, not the work — visit.all must find it.
    visits = [_v(comment="TOS reviewed in passing")]
    assert visits_satisfy(visits, [parse_expression('visit.all ~ "TOS reviewed"')])


def test_same_visit_and_for_positives():
    # A single visit must satisfy BOTH — the remote visit's work matches.
    visits = [
        _v(work="TOS reviewed", vtype="on_site"),
        _v(work="firmware", vtype="remote"),
    ]
    assert (
        visits_satisfy(
            visits,
            [
                parse_expression('visit.work ~ "TOS"'),
                parse_expression("visit.type = remote"),
            ],
        )
        is False
    )
    visits = [_v(work="TOS reviewed", vtype="remote")]
    assert visits_satisfy(
        visits,
        [
            parse_expression('visit.work ~ "TOS"'),
            parse_expression("visit.type = remote"),
        ],
    )


def test_visit_type_and_participants():
    visits = [_v(vtype="remote", participants="bgo@vedur.is")]
    assert visits_satisfy(visits, [parse_expression("visit.type = remote")])
    assert visits_satisfy(visits, [parse_expression("visit.participants ~ bgo")])
    # participants matches the RESOLVED NAME too.
    visits = [_v(participants="someone@vedur.is")]
    assert visits_satisfy(visits, [parse_expression("visit.participants ~ Benedikt")])


def test_visit_work_null_is_universal_absence():
    assert visits_satisfy([_v(work=None)], [parse_expression("visit.work = null")])
    assert not visits_satisfy([_v(work="x")], [parse_expression("visit.work = null")])
    assert visits_satisfy([_v(work="x")], [parse_expression("visit.work != null")])


def test_visit_regex():
    visits = [_v(work="TOS reviewed and corrected")]
    assert visits_satisfy(
        visits, [parse_expression("visit.work ~ re:TOS (reviewed|corrected)")]
    )


def test_visit_is_a_discoverable_selectors_topic():
    from tostools import search_selectors as sel

    assert sel.resolve_topic("visit") == sel.TOPIC_VISIT
    group = sel.visit_group()
    selectors = [e.selector for e in group.entries]
    assert selectors == [
        "visit.work",
        "visit.comment",
        "visit.remaining",
        "visit.all",
        "visit.type",
        "visit.participants",
    ]
