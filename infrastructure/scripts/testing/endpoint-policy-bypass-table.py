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
    0  both columns are where they are declared to be
    1  either column moved
    2  the table itself could not be loaded

## Both columns gate — CTO condition 2 on #111

The gateway column gates at **zero**: it is the function that opens the socket.

The control-API column gates at **exactly `CONTROL_BASELINE`**, a recorded number rather
than zero, and it fails in *both* directions.

That reading is deliberate and it is worth stating, because "gates" could also mean "must
be zero today". It cannot mean that here: `contracts/model_policy.py` has 34 known
mismatches tracked on #93 and owned by another seat, so a hard zero would make this PR —
and every unrelated PR — unmergeable for a defect none of them introduced. What the CTO's
objection was actually about is that the number could not fail, and now it can:

  - **A regression fails.** Re-opening a bypass in the control API's validator breaks the
    build. That file is wired to a Django system check that stops startup, so a regression
    there means an endpoint boots clean that this gateway would refuse mid-mission — the
    inverted-gate problem D-050 was raised about.
  - **An improvement also fails**, until the baseline is lowered in the same commit. That
    keeps the number in this file true rather than stale, and makes every step of #93
    visible as a diff.

When the consolidation lands there is one implementation, the baseline is 0, and this is a
plain gate with nothing to explain.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Mismatches `contracts/model_policy.py` is known to have, measured 2026-08-08 against
#: `main` at 66c3057 (34 of the original 60 cases), then re-measured after adding
#: the SEC-24 and SEC-25 regression cases (39 of 68), and lowered again after the
#: control validator picked up the service-name and private-suffix fixes (18 of 68).
#: Lower it in the same commit that fixes cases; the script fails if it is stale in
#: either direction. Goes to 0 when D-050's consolidation lands.
CONTROL_BASELINE = 18

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
    parser.add_argument(
        "--control-baseline",
        type=int,
        default=CONTROL_BASELINE,
        help="exact number of mismatches contracts/model_policy.py is expected to have. "
        "Anything else fails, in either direction.",
    )
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
        # SEC-25's own regression case is a ~60,000-character URL. Printed in full it would
        # make every run of this script (and every CI log) balloon by tens of kilobytes for
        # no benefit — the case is identified by its label, not by staring at the payload.
        shown_url = (
            case.url if len(case.url) <= 80 else f"{case.url[:60]}…[{len(case.url)} chars total]"
        )
        print(
            f"{case.expected!s:7s} {gateway_cell:38s} {control_cell:13s} "
            f"{case.label[:38]:38s} {shown_url!r}"
        )

    print()
    if gateway is not None:
        print(f"GATEWAY  mismatches: {gateway_mismatches} of {len(cases)}")
    if control is not None:
        print(
            f"CONTROL  mismatches: {control_mismatches} of {len(cases)}  "
            f"(gated at exactly {args.control_baseline})"
        )

    failed = False

    if gateway is not None and gateway_mismatches != 0:
        print(
            f"\nFAIL: the gateway policy has {gateway_mismatches} mismatch(es). It is the "
            "function that opens the socket; it gates at zero.",
            file=sys.stderr,
        )
        failed = True

    if control is not None and control_mismatches != args.control_baseline:
        direction = "REGRESSED" if control_mismatches > args.control_baseline else "improved"
        print(
            f"\nFAIL: contracts/model_policy.py has {control_mismatches} mismatches, "
            f"expected exactly {args.control_baseline} — it {direction}.\n"
            + (
                "Something re-opened a bypass in the control API's validator. That file is\n"
                "wired to a Django system check that stops startup, so a regression there\n"
                "means an endpoint boots clean that this gateway would refuse mid-mission."
                if control_mismatches > args.control_baseline
                else "That is good news and it still fails, on purpose. Lower\n"
                f"CONTROL_BASELINE in this script to {control_mismatches} in the same commit\n"
                "that fixed the cases, so the number in the file stays true. When the\n"
                "consolidation lands (D-050) there is one implementation, the baseline is 0,\n"
                "and this becomes a plain gate."
            ),
            file=sys.stderr,
        )
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
