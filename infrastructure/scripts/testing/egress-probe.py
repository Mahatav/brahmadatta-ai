#!/usr/bin/env python3
"""Attempt outbound network access and report, per target, whether it succeeded.

Run inside a container to find out what that container can actually reach. Drives
infrastructure/scripts/egress-test.sh, and is deliberately dependency-free so it can be
executed inside any of the stack's images with a bind mount and no install step.

Targets, and why each one is here:

  169.254.169.254:80   Cloud metadata. The reason C4 exists: a base-URL validator that
                       accepts private ranges accepts this, and on a rented VM it hands
                       out instance credentials. If this is reachable, the "no external
                       inference API" invariant is enforced by nothing.
  1.1.1.1:443          Plain internet by IP, no DNS involved. Catches a container that
                       has a route out even though name resolution is broken.
  api.openai.com:443   A real hosted inference endpoint, by name. Exercises DNS and route
                       together, and names the thing the invariant is actually about.
  registry.npmjs.org:443  Egress that is legitimate for the dependency installer and for
                       nothing else.

Exit code 0 always; the caller reads the JSON and decides what should have failed. That
separation matters — a probe that decides policy is a probe you cannot reuse for the
container that is *supposed* to have egress.
"""

from __future__ import annotations

import json
import socket
import sys
import time

TIMEOUT = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0

TARGETS = [
    ("cloud-metadata", "169.254.169.254", 80),
    ("internet-by-ip", "1.1.1.1", 443),
    ("hosted-inference-api", "api.openai.com", 443),
    ("npm-registry", "registry.npmjs.org", 443),
]


def probe(host: str, port: int) -> dict[str, object]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), TIMEOUT):
            return {
                "reached": True,
                "detail": "connected",
                "seconds": round(time.monotonic() - started, 3),
            }
    except OSError as exc:
        return {
            "reached": False,
            "detail": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.monotonic() - started, 3),
        }


def main() -> int:
    results = {name: probe(host, port) for name, host, port in TARGETS}
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
