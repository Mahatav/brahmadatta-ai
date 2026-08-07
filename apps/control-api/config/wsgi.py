"""WSGI entrypoint, kept for management tooling only.

Serving the API over WSGI breaks the SSE event stream. Deployments use
`config.asgi:application`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
