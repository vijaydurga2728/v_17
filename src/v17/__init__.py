from __future__ import annotations

import contextlib as _contextlib
import sys as _sys

__version__ = "0.0.1"

# smartmoneyconcepts prints a thank-you banner with unicode on import; Windows
# default cp1252 stdout crashes on it. Reconfigure stdout/stderr to UTF-8
# before anything else so any downstream smc import succeeds.
for _stream in (_sys.stdout, _sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        with _contextlib.suppress(Exception):
            _reconfigure(encoding="utf-8", errors="replace")
