"""Standalone script invoked as a real, separate OS process (via subprocess, not
multiprocessing.Process) to attempt one claim_job() call against a real Postgres DB.
Used by test_sec171_adversarial.py::test_claim_job_across_real_separate_processes.

Usage: python _sec171_claim_subprocess.py <worker_id>
Prints the claimed job id (or "NONE") to stdout as the last line.
"""
from __future__ import annotations

import os
import sys

# python <script>.py puts the script's own directory on sys.path[0], not the cwd --
# add the control-api app root (two levels up from orchestrator/tests/) so `config`
# and the other top-level packages resolve the same way manage.py's own sys.path
# setup would.
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

import django  # noqa: E402

django.setup()

from django.utils import timezone  # noqa: E402
from orchestrator import queue  # noqa: E402


def main() -> None:
    worker_id = sys.argv[1]
    job = queue.claim_job(worker_id, now=timezone.now())
    print(str(job.id) if job else "NONE")


if __name__ == "__main__":
    main()
