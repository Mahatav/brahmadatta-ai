"""Brahmadatta model gateway.

The component that decides what a model is allowed to see, where it is allowed to be, and
what the system is allowed to say about the answer.

Nothing in here is imported by the ASGI process. `tests/architecture/test_import_direction.py`
enforces that: an inference client inside the request path is an inference client in the
process holding operator credentials and repository snapshots.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
