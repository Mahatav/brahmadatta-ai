from __future__ import annotations

from django.apps import AppConfig


class MissionsConfig(AppConfig):
    name = "missions"
    verbose_name = "Brahmadatta missions"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Registers JobKind executors/transition policies against
        # orchestrator.executors's EXECUTOR_REGISTRY/TRANSITION_POLICY_REGISTRY (#168).
        # `missions` is the one app guaranteed to load on every process that touches
        # the Job/Mission models (manage.py check, runserver, ASGI, and the future
        # run_worker/run_orchestrator commands alike), so it is the reliable place to
        # import a stage's registration module even before those management commands'
        # own explicit-import mechanism exists — see orchestrator/executors.py's module
        # docstring ("Two halves of the contract") for why the import has to happen
        # somewhere before the dispatch loop starts.
        #
        # Add one line here per JobKind executor module as each stage lands (T1-T6);
        # this is deliberately a flat list, not magic auto-discovery, so a stage that
        # forgot to register is a visible NotImplementedError, not a silent no-op.
        from orchestrator import (
            correlate_executor,  # noqa: F401
            patch_generate_executor,  # noqa: F401
            teardown_executor,  # noqa: F401
        )
        from workers.baseline import dispatch  # noqa: F401
