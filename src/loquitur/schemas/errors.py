"""The base of the exceptions this package raises on purpose."""

from __future__ import annotations


class LoquiturSchemasError(Exception):
    """Base class of the exceptions ``loquitur.schemas`` defines.

    Each public exception also keeps the built-in base it has always had (``ValueError``,
    ``FileNotFoundError``), so existing handlers keep working; ``except LoquiturSchemasError``
    catches all of them and nothing a library underneath raised.
    """
