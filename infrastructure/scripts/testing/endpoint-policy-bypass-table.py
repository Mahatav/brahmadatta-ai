#!/usr/bin/env python3
"""Run the SEC-02 bypass table against both endpoint policies and print the comparison.

`cybersecurity` reserved re-running this table personally before SEC-02 (#93) closes. This
is that table, in a form that can be re-run without retyping a URL — and it deliberately
evaluates **two** implementations side by side, because there are two:

  gateway   services/model-gateway/gateway/endpoint_policy.py
            The model gateway's egress function. The process that actually opens the
            socket. Rewritten on this branch; every case below is expected to be correct.

  control   apps/control-api/contracts/model_policy.py
            The startup validator in the ASGI process. **Not touched on this branch** —
            `tests/architecture/test_import_direction.py` (C5) forbids the ASGI process
            from importing `gateway`, and that file belongs to the control-api seat. It is
            evaluated here so that its remaining failures are visible as a number rather
            than as an assumption. Its column is expected to show mismatches until #93.

The cases and their expected verdicts live in one place —
`services/model-gateway/gateway/tests/bypass_table.py` — shared with the pytest suite, so
the script and the test cannot disagree about what "correct" means.

    python3 infrastructure/scripts/testing/endpoint-policy-bypass-table.py
    python3 infrastructure/scripts/testing/endpoint-policy-bypass-table.py --only gateway

Exit codes:
    0  the gateway policy matches the table on every case
    1  the gateway policy has at least one mismatch
    2  the table itself could not be loaded

The control-API column never affects the exit code. Making this script red for a defect
that is tracked on another issue and owned by another seat would make it useless as a gate
on this one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GATEWAY = REPO_ROOT / "services" / "model-gateway"
CONTROL_API = REPO_ROOT / "apps" / "control-api"


def _load_table():
    if str(GATEWAY) not in sys.path:
        sys.path.insert(0, str(GATEWAY))
    try:
        from gateway.tests.bypass_table import CASES, DECLARED_SERVICE_NAMES
    except Exception as exc:
        print(f"cannot load the bypass table from {GATEWAY}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    return CASES, DECLARED_SERVICE_NAMES


def _gateway_policy():
    try:
        from gateway.endpoint_policy import classify
    except Exception as exc:
        print(f"cannot import the gateway policy: {exc}", file=sys.stderr)
        return None

    def evaluate(url: str, service_names) -> tuple[bool, str]:
        decision = classify(url, service_names=service_names)
        return decision.allowed, decision.rule

    return evaluate


def _control_policy():
    """The control API's validator, imported without booting a Django project.

    Returns None (and the column is skipped, loudly) if the control API or Django is not
    present. A missing column is reported; it is never silently treated as a pass.
    """
    if not (CONTROL_API / "contracts" / "model_policy.py").is_file():
        return None
    if str(CONTROL_API) not in sys.path:
        sys.path.insert(0, str(CONTROL_API))
    try:
        from django.conf import settings as django_settings

        if not django_settings.configured:
            django_settings.configure(
                DEBUG=False,
                SECRET_KEY="bypass-table-not-a-real-secret",  # noqa: S106
                INSTALLED_APPS=[],
                DATABASES={},
                USE_TZ=True,
            )
        from contracts.model_policy import is_local_inference_endpoint
    except Exception as exc:
        print(f"note: control-api policy not evaluated here ({exc})\n", file=sys.stderr)
        return None

    def evaluate(url: str, service_names) -> tuple[bool, str]:
        # The control-API function has no service-name parameter; that is one of the four
        # SEC-02 fixes it is still missing.
        return is_local_inference_endpoint(url), ""

    return evaluate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=["gateway", "control"], default=None)
    parser.add_argument("--quiet", action="store_true", help="print mismatches only")
    args = parser.parse_args(argv)

    cases, declared = _load_table()

    gateway = _gateway_policy() if args.only != "control" else None
    control = _control_policy() if args.only != "gateway" else None

    if gateway is None and control is None:
        print("no policy implementation could be loaded", file=sys.stderr)
        return 2

    print(f"declared MODEL_SERVICE_NAMES: {', '.join(sorted(declared)) or '(none)'}")
    print(f"{len(cases)} cases\n")
    header = f"{'EXPECT':7s} {'GATEWAY — verdict and rule':38s} {'CONTROL':13s} {'LABEL':38s} URL"
    print(header)
    print("-" * len(header))

    gateway_mismatches = 0
    control_mismatches = 0

    for case in cases:
        gateway_cell = "—"
        if gateway is not None:
            allowed, rule = gateway(case.url, declared)
            ok = allowed is case.expected
            gateway_mismatches += 0 if ok else 1
            gateway_cell = f"{'[ok  ]' if ok else '[FAIL]'} {allowed!s:5s} {rule}"[:38]

        control_cell = "—"
        if control is not None:
            allowed, _ = control(case.url, declared)
            ok = allowed is case.expected
            control_mismatches += 0 if ok else 1
            control_cell = f"{'[ok  ]' if ok else '[FAIL]'} {allowed!s:5s}"

        if args.quiet and "[FAIL]" not in gateway_cell + control_cell:
            continue
        print(
            f"{case.expected!s:7s} {gateway_cell:38s} {control_cell:13s} "
            f"{case.label[:38]:38s} {case.url!r}"
        )

    print()
    if gateway is not None:
        print(f"GATEWAY  mismatches: {gateway_mismatches} of {len(cases)}")
    if control is not None:
        print(f"CONTROL  mismatches: {control_mismatches} of {len(cases)}")
        print(
            "\nThe control-api column is contracts/model_policy.py, which this branch does\n"
            "not modify — C5 forbids the ASGI process importing the gateway, and that file\n"
            "belongs to the control-api seat. Its mismatches are tracked on issue #93 and\n"
            "do not affect this script's exit code."
        )

    return 0 if gateway_mismatches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
