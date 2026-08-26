"""Tests for ``tos station set`` / ``tos station describe``.

Covers the shared write core :func:`tostools.tos._station_set_attribute`
without touching the network: date default from ``date_start``, idempotent
no-op, in-place PATCH on a changed open value, and ADD on an absent code.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tostools.tos import _station_date_start, _station_set_attribute


def _client_with_date_start(date_start: str) -> MagicMock:
    client = MagicMock()
    client.get_entity_history.return_value = {
        "attributes": [{"code": "date_start", "value": f"{date_start} 00:00"}]
    }
    return client


def test_date_start_read():
    assert _station_date_start(_client_with_date_start("1993-06-08"), 4235) == "1993-06-08"


def test_missing_date_start_returns_none():
    client = MagicMock()
    client.get_entity_history.return_value = {"attributes": []}
    assert _station_date_start(client, 4235) is None


def test_add_when_absent(capsys):
    client = _client_with_date_start("1993-06-08")
    writer = MagicMock()
    writer.dry_run = False
    writer.get_attribute_values.return_value = []
    with patch("tostools.tos._resolve_parent_id", return_value=4235):
        rc = _station_set_attribute(
            station="AUST", code="description", value="text", date=None,
            client=client, writer=writer,
        )
    assert rc == 0
    writer.add_attribute_value.assert_called_once_with(4235, "description", "text", "1993-06-08")


def test_noop_when_identical(capsys):
    client = _client_with_date_start("1993-06-08")
    writer = MagicMock()
    writer.dry_run = False
    writer.get_attribute_values.return_value = [
        {"id_attribute_value": 1, "value": "text", "date_from": "1993-06-08", "date_to": None}
    ]
    with patch("tostools.tos._resolve_parent_id", return_value=4235):
        rc = _station_set_attribute(
            station="AUST", code="description", value="text", date=None,
            client=client, writer=writer,
        )
    assert rc == 0
    writer.patch_attribute_value.assert_not_called()
    writer.add_attribute_value.assert_not_called()
    assert "no-op" in capsys.readouterr().out


def test_patch_when_changed(capsys):
    client = _client_with_date_start("1993-06-08")
    writer = MagicMock()
    writer.dry_run = False
    writer.get_attribute_values.return_value = [
        {"id_attribute_value": 1, "value": "old", "date_from": "1993-06-08", "date_to": None}
    ]
    with patch("tostools.tos._resolve_parent_id", return_value=4235):
        rc = _station_set_attribute(
            station="AUST", code="description", value="new", date=None,
            client=client, writer=writer,
        )
    assert rc == 0
    writer.patch_attribute_value.assert_called_once_with(1, value="new")


def test_explicit_date_overrides_default():
    client = _client_with_date_start("1993-06-08")
    writer = MagicMock()
    writer.dry_run = False
    writer.get_attribute_values.return_value = []
    with patch("tostools.tos._resolve_parent_id", return_value=4235):
        _station_set_attribute(
            station="AUST", code="description", value="text", date="2020-01-01",
            client=client, writer=writer,
        )
    writer.add_attribute_value.assert_called_once_with(4235, "description", "text", "2020-01-01")
