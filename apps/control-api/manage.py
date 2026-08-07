#!/usr/bin/env python
"""Django management entrypoint for the Brahmadatta AI control API."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - environment problem, not logic
        raise ImportError(
            "Django is not importable. Activate the virtualenv "
            "(apps/control-api/.venv) and install requirements.txt."
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
