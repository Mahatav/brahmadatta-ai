"""The bypass table. Not a test module — the data, so two callers can share it.

Every case here was written down by a reviewer, not invented. `SOURCE` on each row says
which one and where, so `cybersecurity` can map a row back to the finding it came from and
check that nothing was quietly dropped. The sources:

  SEC-02   docs/09-company/08-security-review.md §2, "Executed proof — the policy function"
           (13 rows) and §12.2, the re-run inside the built finale image (11 rows, of which
           `http://0.0.0.0:8080/` is new).
  QA       docs/09-company/11-qa-report.md §3, "Invariant 1 — I attacked this rather than
           confirming it" (30 rows, 19 mismatches, including the decimal-encoded public
           IPv4 that is not in the security review).
  #78      The issue body's own three examples.
  SEC-24   PR #111 round-3 security review. `_classify_address` fed the unwrapped address
           to the allow loop as well as the deny loop, so a 6to4/NAT64 literal wrapping a
           private or loopback address was permitted while delivery actually goes through
           a translation relay outside this policy's visibility — a claim about "the
           embedded address is private" standing in for "this destination is inside our
           trust boundary" when the two are not the same thing once a relay is involved.
  SEC-25   PR #111 round-3 security review, then independently re-verified after an
           orchestrator correction did not reproduce and was itself corrected. `idna`'s
           ContextO check is O(N) per codepoint and is called once per codepoint in a
           label — O(N²) — for scripts like Arabic-Indic digits, checked *before* idna's
           own length validation runs. The advisory's payload (U+0660 repeated, no dots,
           one label) measured 99.8s-122.5s through this exact call site on `idna==3.10`.
           This table carries the verdict case (refused, and fast); the wall-clock
           assertion is `test_sec_25_long_host_does_not_hang` in
           `test_endpoint_policy.py`, since timing does not belong in a shared
           cross-implementation table.

`gateway/tests/test_endpoint_policy.py` runs it as pytest parameters.
`infrastructure/scripts/testing/endpoint-policy-bypass-table.py` runs the same rows against
both this package's policy and the control API's `contracts.model_policy`, so the two can
be compared without anyone retyping a URL.

The `expected` column is the *correct* answer, not the current one.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CASES", "DECLARED_SERVICE_NAMES", "Case"]

#: The service-name allowlist the table is evaluated under. Deliberately small: `main`'s
#: control-API tests treat `small-model` as allowed because it has no dots, and this table
#: keeps it allowed for the *right* reason — somebody declared it.
DECLARED_SERVICE_NAMES = frozenset({"small-model", "model-host.internal"})


@dataclass(frozen=True)
class Case:
    url: str
    expected: bool
    label: str
    source: str


CASES: tuple[Case, ...] = (
    # -- controls: these must keep working, or the fix is not a fix -------------------
    Case("http://127.0.0.1:8080/v1", True, "loopback (control)", "SEC-02 §2"),
    Case("http://127.0.0.1:8000/v1", True, "loopback (control)", "QA §3"),
    Case("http://localhost:8000/v1", True, "localhost by name (control)", "main tests"),
    Case("http://[::1]:8000/v1", True, "IPv6 loopback (control)", "main tests"),
    Case("http://10.0.0.5:8000/v1", True, "RFC 1918 10/8 (control)", "main tests"),
    Case("http://192.168.1.20:8000/v1", True, "RFC 1918 192.168/16 (control)", "main tests"),
    Case("http://172.16.4.4:8000/v1", True, "RFC 1918 172.16/12 (control)", "main tests"),
    Case("http://small-model:8000/v1", True, "declared compose service", "QA §3"),
    Case(
        "http://model-host.internal:8000/v1",
        True,
        "declared internal name",
        "gateway",
    ),
    Case("http://[fd12:3456:789a::1]:8000/v1", True, "IPv6 unique-local (control)", "gateway"),
    # -- already correct before the fix; regressions here would be silent -------------
    Case("https://api.openai.com/v1", False, "hosted provider", "SEC-02 §2"),
    Case("http://API.OPENAI.COM/v1", False, "uppercase provider", "SEC-02 §2"),
    Case("https://api.openai.com./v1", False, "trailing-dot FQDN", "SEC-02 §2"),
    Case("https://eu.api.openai.com/v1", False, "provider subdomain", "main tests"),
    Case("http://xn--api-2h3ea1a.com/v1", False, "punycode label", "QA §3"),
    Case("http://user:pass@api.openai.com/v1", False, "userinfo + real provider", "QA §3"),
    Case("http://[::ffff:104.18.7.1]/v1", False, "IPv4-mapped public", "QA §3"),
    Case("http://[::ffff:8.8.8.8]/v1", False, "IPv4-mapped 8.8.8.8", "QA §3"),
    Case("http://[64:ff9b::808:808]/v1", False, "NAT64 bracketed", "QA §3"),
    Case("http://api.openai.com/v1#.internal", False, "fragment ends .internal", "QA §3"),
    Case("http://8.8.8.8:8000/v1", False, "public IPv4", "main tests"),
    Case("ftp://small-model.internal/v1", False, "non-HTTP scheme", "main tests"),
    Case("", False, "empty setting", "main tests"),
    Case(
        "https://inference.some-startup.example.com/v1",
        False,
        "public host, on no denylist",
        "main tests",
    ),
    # -- the ten SEC-02 bypasses ------------------------------------------------------
    Case("http://169.254.169.254/", False, "AWS/Azure/GCP metadata IP", "SEC-02 §12.2"),
    Case(
        "http://169.254.169.254/latest/meta-data/",
        False,
        "AWS/Azure/GCP IMDSv1",
        "QA §3",
    ),
    Case(
        "http://[fd00:ec2::254]/latest/meta-data/",
        False,
        "EC2 IMDS over IPv6",
        "SEC-02 §12.2",
    ),
    Case(
        "http://metadata.google.internal/computeMetadata/v1/",
        False,
        "GCP metadata by name",
        "SEC-02 §12.2",
    ),
    Case(
        "http://100.100.100.200/latest/meta-data/",
        False,
        "Alibaba metadata (CGNAT)",
        "SEC-02 §12.2",
    ),
    Case("http://metadata.internal/", False, "bare 'metadata' label", "SEC-02 §12.2"),
    Case("http://api。openai。com/v1", False, "IDNA homograph U+3002", "SEC-02 §12.2"),
    Case("http://openai/v1", False, "bare label", "SEC-02 §12.2"),
    Case(
        "http://[::ffff:169.254.169.254]/",
        False,
        "IPv4-mapped metadata",
        "SEC-02 §12.2",
    ),
    Case("http://0.0.0.0:8080/", False, "unspecified address", "SEC-02 §12.2"),
    # -- #78's own examples -----------------------------------------------------------
    Case(
        "https://my-llm-proxy.internal/v1",
        False,
        "undeclared .internal proxy — named in issue #78",
        "#78",
    ),
    # -- QA's additions on top of SEC-02 ----------------------------------------------
    Case("http://api．openai．com/v1", False, "IDNA homograph U+FF0E fullwidth", "QA §3"),
    Case(
        "http://api.openai.com.evil.test/v1",
        False,
        ".test suffix wraps a provider name",
        "QA §3",
    ),
    Case("http://evil.internal/v1", False, "attacker-controlled .internal", "QA §3"),
    Case(
        "http://api.openai.com:443@evil.local/v1",
        False,
        "userinfo confusion",
        "QA §3",
    ),
    Case("http://2130706433/v1", False, "decimal-encoded 127.0.0.1", "QA §3"),
    Case("http://134744072/v1", False, "decimal-encoded 8.8.8.8", "QA §3"),
    Case("http://0x7f000001/v1", False, "hex-encoded loopback", "QA §3"),
    Case("http://017700000001/v1", False, "octal-encoded loopback", "gateway"),
    Case("http://64:ff9b::808:808/v1", False, "NAT64 unbracketed -> 8.8.8.8", "QA §3"),
    Case("http://[::]/v1", False, "unspecified IPv6", "QA §3"),
    Case(
        "http://169.254.170.2/v2/credentials",
        False,
        "ECS task credentials endpoint",
        "QA §3",
    ),
    Case("http://sneaky.svc/v1", False, "attacker .svc suffix", "QA §3"),
    Case("http://redirector.local/v1", False, "mDNS name resolving outward", "QA §3"),
    Case("http://192.0.2.1/v1", False, "TEST-NET-1 documentation range", "QA §3"),
    Case("https://198.51.100.7/v1", False, "TEST-NET-2 documentation range", "main tests"),
    # -- neighbours of the above, added here rather than discovered later --------------
    Case("http://[2002:808:808::1]/v1", False, "6to4 wrapper around 8.8.8.8", "gateway"),
    Case("http://metadata.goog/computeMetadata/v1/", False, "GCP metadata.goog", "gateway"),
    Case("http://metadata/", False, "single-label metadata", "gateway"),
    Case(
        "http://instance-data.ec2.internal/latest/meta-data/",
        False,
        "EC2 instance-data by name",
        "gateway",
    ),
    Case("http://255.255.255.255/v1", False, "IPv4 broadcast", "gateway"),
    Case("http://224.0.0.1/v1", False, "IPv4 multicast", "gateway"),
    Case("http://[fe80::1]/v1", False, "IPv6 link-local", "gateway"),
    Case("https://model.svc.cluster.local/v1", False, "undeclared cluster DNS", "main tests"),
    Case("http://small-model.internal:8000/v1", False, "undeclared .internal", "main tests"),
    Case("http://model-host.local:8000/v1", False, "undeclared .local", "main tests"),
    # -- SEC-24: 6to4/NAT64 wrapping a private or loopback address -------------------
    # Previously allowed: _classify_address fed the unwrapped address to the allow loop
    # as well as the deny loop, so these read as "a private address" when what they
    # actually are is a translation path outside this policy's visibility.
    Case("http://[2002:a00:1::]/v1", False, "6to4 wrapper around 10.0.0.1 (private)", "SEC-24"),
    Case("http://[2002:7f00:1::]/v1", False, "6to4 wrapper around 127.0.0.1 (loopback)", "SEC-24"),
    Case("http://[64:ff9b::a00:1]/v1", False, "NAT64 wrapper around 10.0.0.1 (private)", "SEC-24"),
    Case(
        "http://[64:ff9b::7f00:1]/v1",
        False,
        "NAT64 wrapper around 127.0.0.1 (loopback)",
        "SEC-24",
    ),
    Case(
        "http://[2002:a9fe:a9fe::]/v1",
        False,
        "6to4 wrapper around 169.254.169.254 (link-local/metadata)",
        "SEC-24",
    ),
    Case(
        "http://[::ffff:10.0.0.1]/v1",
        True,
        "ipv4-mapped notation around 10.0.0.1 — control, must stay allowed (SEC-24 fix "
        "does not touch this mechanism)",
        "SEC-24",
    ),
    # -- SEC-25: idna ContextO quadratic-complexity DoS -------------------------------
    # The advisory's own payload: U+0660 (ARABIC-INDIC DIGIT ZERO) x 60000, no dots, one
    # label. Verdict only here; the wall-clock assertion is a dedicated test, since
    # timing does not belong in a table shared with the control-api comparison script.
    Case("http://" + ("٠" * 60_000) + "/v1", False, "idna ContextO DoS payload (60k)", "SEC-25"),
    Case("http://" + ("a" * 300) + "/v1", False, "300-char single label, ordinary ASCII", "SEC-25"),
)
