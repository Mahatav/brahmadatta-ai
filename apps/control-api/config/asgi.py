"""ASGI entrypoint.

The control API runs under ASGI because the Command Center consumes an SSE stream
(`GET /api/v1/missions/{id}/events`); WSGI cannot hold that connection open without a
worker per viewer. Run it with:

    uvicorn config.asgi:application --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()
