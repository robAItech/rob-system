"""hello_probe — javni API paketa.

Re-eksportira javno funkcijo ``greet``, da je dostopna kot
``from hello_probe import greet``.
"""

from .hello_probe import greet

__all__ = ["greet"]