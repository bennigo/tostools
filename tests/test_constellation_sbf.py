"""Tests for the raw-SBF constellation fallback.

Why this exists: RINEX 2 headers carry no per-system list, so an R2 reading is a
lower bound and its ABSENCE of Galileo/BeiDou proves nothing. The IMO archive is
R2 until 2026, which makes 2017-2025 unreadable from headers alone. The SBF
records what was really tracked, so decoding one file recovers the truth.

The contract these pin down:
  * an R3 header is authoritative → never decode (decoding is the slow path)
  * an R2 header → decode the day's raw and prefer that
  * anything missing (no converter, no raw, failed run) → keep the R2 reading,
    never raise, so the audit still runs on a host without sbf2rin
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tostools.constellation import ConstellationReading
from tostools.constellation_sbf import (
    raw_for_rinex,
    read_constellations_sbf_first,
    sbf2rin_available,
    systems_from_sbf,
)

R3 = ConstellationReading(
    version=3.04, systems=frozenset({"GPS", "GLO", "GAL"}), reliable=True
)
R2 = ConstellationReading(version=2.11, systems=frozenset({"GPS"}), reliable=False)
DECODED = ConstellationReading(
    version=3.04, systems=frozenset({"GPS", "GLO", "GAL", "BDS"}), reliable=True
)


def _archive(tmp_path: Path, *, rinex="ISAK1110.26D.Z", raws=()) -> Path:
    """Build a <session>/{rinex,raw}/ pair mirroring the real archive layout."""
    base = tmp_path / "2026" / "apr" / "ISAK" / "15s_24hr"
    (base / "rinex").mkdir(parents=True)
    (base / "raw").mkdir(parents=True)
    rp = base / "rinex" / rinex
    rp.write_text("dummy")
    for name in raws:
        (base / "raw" / name).write_bytes(b"\x00")
    return rp


class TestRawForRinex:
    def test_finds_same_day_raw(self, tmp_path):
        rp = _archive(tmp_path, raws=("ISAK202604210000a.sbf.gz",))
        found = raw_for_rinex(rp)
        assert found is not None and found.name == "ISAK202604210000a.sbf.gz"

    def test_resolves_via_sibling_not_an_archive_root(self, tmp_path):
        """Deliberate: the archive is split across two roots, so deriving the
        raw/ sibling means whichever root the RINEX came from is searched."""
        rp = _archive(tmp_path, raws=("ISAK202604210000a.sbf.gz",))
        assert raw_for_rinex(rp).parent == rp.parent.parent / "raw"

    def test_ignores_a_different_day(self, tmp_path):
        rp = _archive(tmp_path, raws=("ISAK202609090000a.sbf.gz",))
        assert raw_for_rinex(rp) is None

    def test_uncompressed_sbf_also_accepted(self, tmp_path):
        rp = _archive(tmp_path, raws=("ISAK202604210000a.sbf",))
        assert raw_for_rinex(rp) is not None

    def test_no_raw_dir_is_none_not_an_error(self, tmp_path):
        d = tmp_path / "2026" / "apr" / "ISAK" / "15s_24hr" / "rinex"
        d.mkdir(parents=True)
        rp = d / "ISAK1110.26D.Z"
        rp.write_text("x")
        assert raw_for_rinex(rp) is None

    def test_empty_raw_dir_is_none(self, tmp_path):
        assert raw_for_rinex(_archive(tmp_path)) is None

    def test_unparseable_filename_is_none(self, tmp_path):
        rp = _archive(
            tmp_path, rinex="not-a-rinex-name", raws=("ISAK202604210000a.sbf.gz",)
        )
        assert raw_for_rinex(rp) is None


class TestReaderFallback:
    def test_r3_is_authoritative_and_never_decodes(self, tmp_path, monkeypatch):
        """The decode is the slow path — an R3 header must short-circuit it."""
        rp = _archive(tmp_path, raws=("ISAK202604210000a.sbf.gz",))
        monkeypatch.setattr(
            "tostools.constellation_sbf.read_constellations", lambda p: R3
        )
        called = []
        monkeypatch.setattr(
            "tostools.constellation_sbf.systems_from_sbf",
            lambda *a, **k: called.append(1) or DECODED,
        )
        assert read_constellations_sbf_first(rp) is R3
        assert called == [], "decoded despite a reliable R3 header"

    def test_r2_falls_back_to_the_decode(self, tmp_path, monkeypatch):
        rp = _archive(tmp_path, raws=("ISAK202604210000a.sbf.gz",))
        monkeypatch.setattr(
            "tostools.constellation_sbf.read_constellations", lambda p: R2
        )
        monkeypatch.setattr(
            "tostools.constellation_sbf.systems_from_sbf", lambda *a, **k: DECODED
        )
        got = read_constellations_sbf_first(rp)
        assert got is DECODED and got.reliable
        assert "BDS" in got.systems, "R2 could never have reported BeiDou"

    def test_r2_kept_when_no_raw_archived(self, tmp_path, monkeypatch):
        rp = _archive(tmp_path)  # no raw files
        monkeypatch.setattr(
            "tostools.constellation_sbf.read_constellations", lambda p: R2
        )
        assert read_constellations_sbf_first(rp) is R2

    def test_r2_kept_when_decode_fails(self, tmp_path, monkeypatch):
        """A failed conversion must not lose the reading we already had."""
        rp = _archive(tmp_path, raws=("ISAK202604210000a.sbf.gz",))
        monkeypatch.setattr(
            "tostools.constellation_sbf.read_constellations", lambda p: R2
        )
        monkeypatch.setattr(
            "tostools.constellation_sbf.systems_from_sbf", lambda *a, **k: None
        )
        assert read_constellations_sbf_first(rp) is R2

    def test_unreadable_rinex_still_tries_the_raw(self, tmp_path, monkeypatch):
        rp = _archive(tmp_path, raws=("ISAK202604210000a.sbf.gz",))
        monkeypatch.setattr(
            "tostools.constellation_sbf.read_constellations", lambda p: None
        )
        monkeypatch.setattr(
            "tostools.constellation_sbf.systems_from_sbf", lambda *a, **k: DECODED
        )
        assert read_constellations_sbf_first(rp) is DECODED


class TestConverterAbsent:
    def test_missing_converter_returns_none_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tostools.constellation_sbf.shutil.which", lambda _: None)
        assert systems_from_sbf(tmp_path / "nope.sbf.gz") is None

    def test_availability_probe_follows_path(self, monkeypatch):
        monkeypatch.setattr("tostools.constellation_sbf.shutil.which", lambda _: None)
        assert sbf2rin_available() is False
        monkeypatch.setattr(
            "tostools.constellation_sbf.shutil.which", lambda _: "/usr/bin/sbf2rin"
        )
        assert sbf2rin_available() is True

    def test_audit_picks_the_header_reader_without_a_converter(self, monkeypatch):
        """Degrade to previous behaviour rather than fail on a converter-less host."""
        from tostools import audit_constellations as ac
        from tostools.constellation import read_constellations

        monkeypatch.setattr(ac, "sbf2rin_available", lambda: False)
        assert ac._history_reader() is read_constellations

        monkeypatch.setattr(ac, "sbf2rin_available", lambda: True)
        assert ac._history_reader() is read_constellations_sbf_first


class TestDecodeIntegration:
    """Exercises the real subprocess path — skipped where sbf2rin is absent."""

    @pytest.mark.skipif(not sbf2rin_available(), reason="sbf2rin not on PATH")
    def test_garbage_input_fails_closed(self, tmp_path):
        bad = tmp_path / "ISAK202604210000a.sbf"
        bad.write_bytes(b"not an SBF stream")
        assert systems_from_sbf(bad) is None

    def test_archive_is_never_written_to(self, tmp_path, monkeypatch):
        """Conversion happens in a TemporaryDirectory — the failure mode that
        bit the Trimble converter was staging intermediates in the archive."""
        rp = _archive(tmp_path, raws=("ISAK202604210000a.sbf.gz",))
        raw_dir = rp.parent.parent / "raw"
        before = {p.name for p in raw_dir.iterdir()}
        monkeypatch.setattr("tostools.constellation_sbf.shutil.which", lambda _: None)
        systems_from_sbf(raw_dir / "ISAK202604210000a.sbf.gz")
        assert {p.name for p in raw_dir.iterdir()} == before
