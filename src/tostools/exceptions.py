"""Typed exceptions for tostools.

Deliberately small. The one rule worth stating: **library code raises, CLI
entry points decide the exit code.** Library modules here used to call
``sys.exit(1)`` directly on a transport failure, which meant a transient TOS
blip during a multi-hour ``--fix-headers`` or re-rinex run killed the whole
process instead of failing one file.

``TOSConnectionError`` subclasses builtin :class:`ConnectionError` (and so
:class:`OSError`) on purpose, not just :class:`Exception`. Downstream callers
already funnel transport failures through ``except OSError`` — notably
``receivers.rinex.converter_base``, which converts them into its own
``NetworkUnavailableError`` and retries. Inheriting from ``ConnectionError``
means those handlers keep catching this without any downstream change, while
callers who want to be specific can catch ``TOSConnectionError`` directly.
"""

from __future__ import annotations


class TOSError(Exception):
    """Base class for errors originating in tostools."""


class TOSConnectionError(TOSError, ConnectionError):
    """Could not reach the TOS API.

    Raised instead of ``sys.exit(1)`` so a caller can decide whether one
    unreachable request should end the whole run.
    """
