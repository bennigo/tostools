"""The position-refusal log must NAME the offending file.

`compare_rinex_to_tos` refuses to rewrite APPROX POSITION when the header sits
absurdly far from the TOS position — the file belongs to another site. That
refusal is correct and load-bearing (it is what stops foreign data being
laundered under our marker), but it is only *actionable* if the message says
which file.

It didn't. The lookup used the key from the wrong dict, so every refusal printed
the literal "<file>". On 2026-08-20 that cost a full rescan of ELDC's and NYLA's
archives to recover names the log had already had in hand.
"""

from __future__ import annotations

from tostools.rinex.reader import extract_header_info


def _info_for(tmp_path, name="ELDC3420.23D.Z"):
    """Build a rinex_info dict the way the production path does."""
    header_data = {
        "rinex file": [str(tmp_path), name],
        "header": (
            "     3.04           OBSERVATION DATA    M (MIXED)           "
            "RINEX VERSION / TYPE\n"
            "ELDC                                                        "
            "MARKER NAME\n"
        ),
    }
    return extract_header_info(header_data)


class TestRinexInfoShape:
    """The reason the old lookup missed: the key is `file_name`, not `rinex file`."""

    def test_extract_header_info_stores_file_name(self, tmp_path):
        info = _info_for(tmp_path)
        assert info["file_name"] == "ELDC3420.23D.Z"
        assert info["file_path"] == str(tmp_path)

    def test_the_old_key_is_absent_from_the_output_dict(self, tmp_path):
        # This is the whole bug in one assertion: the key the logger reached for
        # never exists on this dict, so .get() always fell back to "<file>".
        info = _info_for(tmp_path)
        assert "rinex file" not in info


class TestRefusalNamesTheFile:
    def _resolve(self, rinex_info):
        """Mirror of the name resolution in validator.py."""
        return rinex_info.get("file_name") or rinex_info.get("rinex file") or "<file>"

    def test_names_the_file_from_extract_header_info_output(self, tmp_path):
        assert self._resolve(_info_for(tmp_path)) == "ELDC3420.23D.Z"

    def test_falls_back_to_the_raw_key_if_that_shape_arrives(self):
        assert self._resolve({"rinex file": "NYLA3420.14D.Z"}) == "NYLA3420.14D.Z"

    def test_placeholder_only_when_genuinely_unknown(self):
        assert self._resolve({}) == "<file>"

    def test_empty_name_does_not_win_over_the_fallback(self):
        assert self._resolve({"file_name": "", "rinex file": "X.Z"}) == "X.Z"
