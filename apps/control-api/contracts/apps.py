from __future__ import annotations

from django.apps import AppConfig


class ContractsConfig(AppConfig):
    name = "contracts"
    verbose_name = "Brahmadatta contract"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Registers the model-endpoint system check. Importing here rather than at
        # module scope keeps the check bound to app startup, so `manage.py check`,
        # `runserver` and ASGI boot all run it.
        from contracts import checks  # noqa: F401
