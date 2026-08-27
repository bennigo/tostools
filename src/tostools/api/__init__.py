"""TOS API client modules."""

from ._http import canonical_tos_url
from .tos_client import TOSClient
from .tos_writer import DryRunResult, TOSWriter

# canonical_tos_url is re-exported so callers reach it through the PUBLIC api
# package rather than `api._http`, a private module. receivers.dissemination
# .tos_access uses it to normalise a TOS base URL.
__all__ = ["TOSClient", "TOSWriter", "DryRunResult", "canonical_tos_url"]
