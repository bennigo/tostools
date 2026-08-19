"""A reason TOS cannot store must not be reported as stored.

``tos visit add`` accepts five reason codes, but TOS auto-seeds an attribute
row only for the ones it actually models — today ``change`` / ``repairs`` /
``improvements``. The PUT builder skips any reason with no seeded row, and it
used to do so in silence: ``--reason inspection`` passed argparse validation,
the CLI printed "Created vitjun id_maintenance=5654", and the record came back
with ``reasons —``. VMEY 5654 is that record.

The write cannot be made to succeed from here — the row does not exist — so the
contract is to say what was dropped and what TOS would have taken.
"""

import logging

import pytest

from tostools.api.tos_writer import TOSWriter


class _FakeWriter(TOSWriter):
    """Drives ``add_maintenance_visit``'s POST → GET → PUT without a server."""

    def __init__(self, seeded_codes):
        self._seeded = seeded_codes
        self.put_values = None

    def _request(self, method, path, data=None, **kw):
        if method == "POST":
            return {"id": 5654}
        self.put_values = data["maintenance_attribute_values"]
        return {"ok": True}

    def get_maintenance_visit(self, id_maintenance):
        # The seeded attribute rows TOS hands back between the POST and PUT.
        return {
            "maintenance_attribute_values": [
                {"code": c, "id_maintenance_attribute_value": 100 + i}
                for i, c in enumerate(self._seeded)
            ]
        }


# What TOS actually seeds on a GPS station vitjun today.
LIVE_CODES = [
    "work",
    "reason_change",
    "reason_improvements",
    "reason_repairs",
    "comment",
    "remaining",
]


def _add(writer, reasons):
    return writer.add_maintenance_visit(
        4430,
        start_time="2026-08-19",
        end_time="2026-08-19",
        participants="bgo@vedur.is",
        completed=True,
        reasons=reasons,
        work="w",
        comment="c",
        remaining=None,
    )


def _written_reasons(writer):
    by_id = {v["id_maintenance_attribute_value"]: v["value"] for v in writer.put_values}
    out = set()
    for i, code in enumerate(LIVE_CODES):
        if code.startswith("reason_") and by_id.get(100 + i) == "true":
            out.add(code[len("reason_") :])
    return out


class TestAnUnstorableReasonIsReported:
    def test_it_warns_and_names_what_tos_accepts(self, caplog):
        w = _FakeWriter(LIVE_CODES)
        with caplog.at_level(logging.WARNING, logger="tostools.api.tos_writer"):
            _add(w, ["inspection"])
        msg = caplog.text
        assert "inspection" in msg
        assert "NOT stored" in msg
        # It must say what WOULD work, not just that something failed.
        for accepted in ("change", "improvements", "repairs"):
            assert accepted in msg

    def test_the_vitjun_is_still_created(self, caplog):
        # Warn, don't fail: the record and its work/comment text are worth
        # keeping; only the reason flag is unstorable.
        w = _FakeWriter(LIVE_CODES)
        with caplog.at_level(logging.WARNING):
            res = _add(w, ["inspection"])
        assert res["id_maintenance"] == 5654

    @pytest.mark.parametrize("reason", ["change", "repairs", "improvements"])
    def test_a_storable_reason_is_written_and_not_warned_about(self, reason, caplog):
        w = _FakeWriter(LIVE_CODES)
        with caplog.at_level(logging.WARNING, logger="tostools.api.tos_writer"):
            _add(w, [reason])
        assert _written_reasons(w) == {reason}
        assert "NOT stored" not in caplog.text

    def test_a_mixed_request_stores_the_storable_half(self, caplog):
        w = _FakeWriter(LIVE_CODES)
        with caplog.at_level(logging.WARNING, logger="tostools.api.tos_writer"):
            _add(w, ["repairs", "inspection"])
        assert _written_reasons(w) == {"repairs"}
        assert "inspection" in caplog.text

    def test_no_reasons_requested_warns_about_nothing(self, caplog):
        w = _FakeWriter(LIVE_CODES)
        with caplog.at_level(logging.WARNING, logger="tostools.api.tos_writer"):
            _add(w, [])
        assert "NOT stored" not in caplog.text

    def test_it_survives_a_record_with_no_reason_rows_at_all(self, caplog):
        w = _FakeWriter(["work", "comment", "remaining"])
        with caplog.at_level(logging.WARNING, logger="tostools.api.tos_writer"):
            _add(w, ["repairs"])
        assert "NOT stored" in caplog.text
        assert "(none)" in caplog.text
