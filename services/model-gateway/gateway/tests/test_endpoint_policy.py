"""SEC-02 / issue #78: the endpoint policy, attacked rather than confirmed.

The table in `bypass_table.py` carries every case the security review and the QA report
executed, each tagged with where it came from. This module runs it, plus the cases that
are about the *shape* of the fix rather than a single URL — the settings allowlist, the
DNS half, and the reasons a decision was reached.

The last one matters more than it looks. A validator can return the right boolean for the
wrong reason and then return the wrong boolean the moment a URL shifts slightly;
`test_each_bypass_is_caught_by_the_rule_that_should_catch_it` pins the rule as well as the
verdict, so a case that starts passing by accident shows up as a failure here.
"""

from __future__ import annotations

import pytest

from gateway.endpoint_policy import (
    assert_local_inference_endpoint,
    assert_resolves_inside_boundary,
    classify,
    is_local_inference_endpoint,
    normalise_service_names,
)
from gateway.errors import ExternalInferenceBlockedError
from gateway.tests.bypass_table import CASES, DECLARED_SERVICE_NAMES, Case


def _ids() -> list[str]:
    return [f"{c.source}::{c.label}" for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=_ids())
def test_bypass_table(case: Case) -> None:
    decision = classify(case.url, service_names=DECLARED_SERVICE_NAMES)
    assert decision.allowed is case.expected, (
        f"{case.label} ({case.source})\n"
        f"  url      : {case.url!r}\n"
        f"  expected : {case.expected}\n"
        f"  got      : {decision.allowed}  [rule={decision.rule}] {decision.reason}"
    )


@pytest.mark.parametrize("case", [c for c in CASES if not c.expected], ids=lambda c: c.label)
def test_blocked_cases_raise(case: Case) -> None:
    assert is_local_inference_endpoint(case.url, service_names=DECLARED_SERVICE_NAMES) is False
    with pytest.raises(ExternalInferenceBlockedError):
        assert_local_inference_endpoint(
            "MODEL_ENDPOINT", case.url, service_names=DECLARED_SERVICE_NAMES
        )


@pytest.mark.parametrize("case", [c for c in CASES if c.expected], ids=lambda c: c.label)
def test_allowed_cases_do_not_raise(case: Case) -> None:
    assert_local_inference_endpoint(
        "MODEL_ENDPOINT", case.url, service_names=DECLARED_SERVICE_NAMES
    )


# --------------------------------------------------------------------------------------
# The right answer for the right reason
# --------------------------------------------------------------------------------------

#: url -> the rule id that must be the one to catch it.
RULE_FOR = {
    "http://169.254.169.254/": "denied-network",
    "http://[fd00:ec2::254]/latest/meta-data/": "denied-network",
    "http://100.100.100.200/latest/meta-data/": "denied-network",
    "http://[::ffff:169.254.169.254]/": "denied-network",
    "http://169.254.170.2/v2/credentials": "denied-network",
    "http://0.0.0.0:8080/": "denied-network",
    "http://[::]/v1": "denied-network",
    "http://192.0.2.1/v1": "denied-network",
    "https://198.51.100.7/v1": "denied-network",
    "http://[fe80::1]/v1": "denied-network",
    "http://metadata.google.internal/computeMetadata/v1/": "metadata-name",
    "http://metadata.internal/": "metadata-name",
    "http://metadata.goog/computeMetadata/v1/": "metadata-name",
    "http://metadata/": "metadata-name",
    "http://instance-data.ec2.internal/latest/meta-data/": "metadata-name",
    "http://api。openai。com/v1": "idna-mismatch",
    "http://api．openai．com/v1": "idna-mismatch",
    "http://API.OPENAI.COM/v1": "hosted-provider",
    "https://api.openai.com/v1": "hosted-provider",
    "http://openai/v1": "undeclared-bare-label",
    "http://2130706433/v1": "packed-ipv4",
    "http://134744072/v1": "packed-ipv4",
    "http://0x7f000001/v1": "packed-ipv4",
    "http://017700000001/v1": "packed-ipv4",
    "http://api.openai.com:443@evil.local/v1": "userinfo",
    "http://user:pass@api.openai.com/v1": "userinfo",
    "https://my-llm-proxy.internal/v1": "undeclared-private-suffix",
    "http://evil.internal/v1": "undeclared-private-suffix",
    "http://sneaky.svc/v1": "undeclared-private-suffix",
    "http://redirector.local/v1": "undeclared-private-suffix",
    "http://api.openai.com.evil.test/v1": "undeclared-private-suffix",
    "http://[::ffff:8.8.8.8]/v1": "global-address",
    "http://[64:ff9b::808:808]/v1": "global-address",
    "http://[2002:808:808::1]/v1": "global-address",
    "ftp://small-model.internal/v1": "scheme",
    # An unbracketed IPv6 literal is not an IPv6 literal to urlsplit: it sees the host as
    # `64` and the rest as a port. `64` is then a dotless integer, which inet_aton reads
    # as 0.0.0.64 — so the packed-IPv4 rule is the one that catches it, and that is the
    # correct rule rather than a lucky one.
    "http://64:ff9b::808:808/v1": "packed-ipv4",
    # SEC-24 — the point of the fix is that these are refused for what they are (a
    # translation path with an illegitimate embedded address), not merely refused.
    "http://[2002:a00:1::]/v1": "translation-wrapper-non-global",
    "http://[2002:7f00:1::]/v1": "translation-wrapper-non-global",
    "http://[64:ff9b::a00:1]/v1": "translation-wrapper-non-global",
    "http://[64:ff9b::7f00:1]/v1": "translation-wrapper-non-global",
    # The embedded address (169.254.169.254) is caught by the more specific deny-list
    # entry before the translation-wrapper check runs — correctly: link-local/metadata is
    # refused for what it is either way, and the deny list is checked first for exactly
    # this reason (SEC-02's fix order, unchanged by SEC-24).
    "http://[2002:a9fe:a9fe::]/v1": "denied-network",
    # SEC-25 — refused before IDNA ever sees the string, not by idna-invalid or any other
    # rule downstream of the codepoint scan.
    "http://" + ("٠" * 60_000) + "/v1": "host-too-long",
    "http://" + ("a" * 300) + "/v1": "host-too-long",
}


@pytest.mark.parametrize("url,rule", sorted(RULE_FOR.items()))
def test_each_bypass_is_caught_by_the_rule_that_should_catch_it(url: str, rule: str) -> None:
    decision = classify(url, service_names=DECLARED_SERVICE_NAMES)
    assert decision.allowed is False
    assert decision.rule == rule, (
        f"{url!r} was refused by {decision.rule!r}, not {rule!r}. Refusing for the wrong "
        "reason means the intended rule is not doing anything and the next URL shape will "
        f"get through. Reason given: {decision.reason}"
    )


# --------------------------------------------------------------------------------------
# The allowlist is a boundary, not a hole
# --------------------------------------------------------------------------------------


def test_default_service_names_are_empty_so_nothing_extra_is_trusted() -> None:
    """Fail-closed. With no declaration, a compose service name is not permitted."""
    assert classify("http://small-model:8000/v1").allowed is False
    assert classify("http://small-model:8000/v1").rule == "undeclared-bare-label"
    # ...and loopback still works, so the documented bare-uvicorn flow is not broken.
    assert classify("http://127.0.0.1:8000/v1").allowed is True
    assert classify("http://localhost:8000/v1").allowed is True


def test_declaring_a_name_permits_exactly_that_name() -> None:
    declared = normalise_service_names(["small-model"])
    assert classify("http://small-model:8000/v1", service_names=declared).allowed is True
    assert classify("http://small-model2:8000/v1", service_names=declared).allowed is False
    assert classify("http://small-model.evil.test/v1", service_names=declared).allowed is False


@pytest.mark.parametrize(
    "entry",
    [
        "api.openai.com",
        "metadata.google.internal",
        "metadata",
        "169.254.169.254",
        "2130706433",
        "api。openai。com",
        "inference.example.com",
        "evil.com",
    ],
)
def test_a_dangerous_service_name_declaration_is_refused_at_startup(entry: str) -> None:
    """The allowlist cannot be used to re-open what the rules just closed."""
    with pytest.raises(ExternalInferenceBlockedError):
        normalise_service_names([entry])


def test_service_names_parse_forgivingly_but_normalise_strictly() -> None:
    assert normalise_service_names([" Small-Model ", "", "model-host.internal."]) == frozenset(
        {"small-model", "model-host.internal"}
    )


# --------------------------------------------------------------------------------------
# "and anything that resolves outward"
# --------------------------------------------------------------------------------------


def test_a_declared_name_that_resolves_to_a_public_address_is_refused() -> None:
    """The case a syntactic validator structurally cannot see.

    `redirector.local` passes every name rule once an operator declares it. It is still a
    name somebody else's DNS answers, and on a laptop with a search domain it answers with
    a public address. The resolver is injected so this is deterministic and needs no
    network.
    """
    declared = normalise_service_names(["redirector.local"])

    with pytest.raises(ExternalInferenceBlockedError) as caught:
        assert_resolves_inside_boundary(
            "MODEL_ENDPOINT",
            "http://redirector.local:8000/v1",
            service_names=declared,
            resolver=lambda host: ["93.184.216.34"],
        )
    assert "resolves to 93.184.216.34" in str(caught.value)


def test_a_declared_name_that_resolves_to_metadata_is_refused() -> None:
    declared = normalise_service_names(["model-host.internal"])
    with pytest.raises(ExternalInferenceBlockedError):
        assert_resolves_inside_boundary(
            "MODEL_ENDPOINT",
            "http://model-host.internal:8000/v1",
            service_names=declared,
            resolver=lambda host: ["169.254.169.254"],
        )


def test_one_public_answer_among_private_ones_is_still_a_refusal() -> None:
    """Every answer is checked, not the first. A round-robin record only has to win once."""
    declared = normalise_service_names(["model-host.internal"])
    with pytest.raises(ExternalInferenceBlockedError):
        assert_resolves_inside_boundary(
            "MODEL_ENDPOINT",
            "http://model-host.internal:8000/v1",
            service_names=declared,
            resolver=lambda host: ["10.0.0.5", "fd00::1", "8.8.8.8"],
        )


def test_a_name_resolving_inside_the_boundary_is_permitted() -> None:
    declared = normalise_service_names(["small-model"])
    assert assert_resolves_inside_boundary(
        "MODEL_ENDPOINT",
        "http://small-model:8000/v1",
        service_names=declared,
        resolver=lambda host: ["10.42.0.9", "::1"],
    ) == ["10.42.0.9", "::1"]


def test_an_address_literal_needs_no_resolution() -> None:
    def explode(host: str) -> list[str]:  # pragma: no cover - must not be called
        raise AssertionError("an address literal must not be sent to a resolver")

    assert assert_resolves_inside_boundary(
        "MODEL_ENDPOINT", "http://127.0.0.1:8000/v1", resolver=explode
    ) == ["127.0.0.1"]


def test_a_name_that_does_not_resolve_is_refused_rather_than_assumed_local() -> None:
    declared = normalise_service_names(["small-model"])

    def fails(host: str) -> list[str]:
        raise OSError("Name or service not known")

    with pytest.raises(ExternalInferenceBlockedError):
        assert_resolves_inside_boundary(
            "MODEL_ENDPOINT",
            "http://small-model:8000/v1",
            service_names=declared,
            resolver=fails,
        )


# --------------------------------------------------------------------------------------
# Error quality — this control gets read by whoever is debugging at 2am
# --------------------------------------------------------------------------------------


def test_the_error_names_the_setting_the_host_and_the_rule() -> None:
    with pytest.raises(ExternalInferenceBlockedError) as caught:
        assert_local_inference_endpoint("MODEL_ENDPOINT", "http://169.254.169.254/")
    message = str(caught.value)
    assert "MODEL_ENDPOINT" in message
    assert "169.254.169.254" in message
    assert caught.value.details["rule"] == "denied-network"


def test_the_homograph_error_shows_what_the_client_would_have_contacted() -> None:
    decision = classify("http://api。openai。com/v1")
    assert "api.openai.com" in decision.reason, (
        "the operator has to be told that the string they typed becomes api.openai.com "
        "once the HTTP client normalises it — that is the whole finding"
    )


# --------------------------------------------------------------------------------------
# SEC-24 — a 6to4/NAT64 literal is a translation path, not a notation
# --------------------------------------------------------------------------------------


def test_6to4_and_nat64_are_refused_regardless_of_the_embedded_address() -> None:
    """The fix in one sentence: unlike ipv4-mapped, these two never reach the allow loop.

    `ipv4_mapped` stays judged by the embedded address — `::ffff:10.0.0.1` is a *notation*
    for an address a dual-stack socket layer already treats as 10.0.0.1, with no relay in
    the path. 6to4 and NAT64 are different: reaching either literal means a relay outside
    this policy's visibility rewrites the packet to the embedded IPv4 destination, so
    "the embedded address is private" was never the same claim as "this destination is
    inside our trust boundary".
    """
    # A public embedded address was already denied before the fix (global-address, via
    # the same effective-address check this fix does not touch) — kept as a control so a
    # future edit cannot narrow the fix down to only the newly-added rule.
    assert classify("http://[2002:808:808::1]/v1").rule == "global-address"

    # The fix: a private or loopback embedded address no longer reaches "allowed-network".
    for url in (
        "http://[2002:a00:1::]/v1",  # 6to4 / 10.0.0.1
        "http://[2002:7f00:1::]/v1",  # 6to4 / 127.0.0.1
        "http://[64:ff9b::a00:1]/v1",  # NAT64 / 10.0.0.1
        "http://[64:ff9b::7f00:1]/v1",  # NAT64 / 127.0.0.1
    ):
        decision = classify(url)
        assert decision.allowed is False
        assert decision.rule == "translation-wrapper-non-global"


def test_ipv4_mapped_notation_is_unaffected_by_the_sec_24_fix() -> None:
    """The one wrapper kind that is still judged by what it carries.

    If this ever starts failing, the fix in `_classify_address` widened past what SEC-24
    asked for — `ipv4_mapped` is a notation, and refusing it would break loopback and
    private addresses reached through a dual-stack socket, which nothing in SEC-24's
    finding asked for.
    """
    assert classify("http://[::ffff:127.0.0.1]/v1").allowed is True
    assert classify("http://[::ffff:10.0.0.1]/v1").allowed is True
    assert classify("http://[::ffff:169.254.169.254]/v1").allowed is False  # denied-network
    assert classify("http://[::ffff:8.8.8.8]/v1").allowed is False  # global-address


def test_the_translation_wrapper_error_names_the_mechanism_and_the_rfc() -> None:
    decision = classify("http://[2002:a00:1::]/v1")
    assert "6to4" in decision.reason
    assert "10.0.0.1" in decision.reason
    assert "RFC 3056" in decision.reason


# --------------------------------------------------------------------------------------
# SEC-25 — the idna ContextO quadratic-complexity DoS, and the fix that survives a
# regression in the library itself
# --------------------------------------------------------------------------------------


def test_sec_25_long_host_does_not_hang() -> None:
    """The advisory's own payload, timed. Refused, and refused fast.

    Reported at 99.8s-122.5s through this exact call site on the previously pinned
    `idna==3.10`. The bound below (2s) is generous by roughly two orders of magnitude —
    tight enough to catch a reintroduction of the bug (by an idna downgrade, or a change
    that calls idna before the length guard), loose enough not to flake on a slow CI
    runner for a check that should complete in well under a millisecond.
    """
    import time

    payload = "٠" * 60_000  # ARABIC-INDIC DIGIT ZERO, the advisory's payload

    started = time.perf_counter()
    decision = classify(f"http://{payload}/v1")
    elapsed = time.perf_counter() - started

    assert decision.allowed is False
    assert decision.rule == "host-too-long", (
        f"expected the length guard to refuse this before IDNA ever ran; got "
        f"rule={decision.rule!r}. If IDNA processing ran at all on this payload, the "
        "guard did not fire ahead of it, which is the exact ordering SEC-25 requires."
    )
    assert elapsed < 2.0, (
        f"took {elapsed:.3f}s. The length guard is supposed to refuse this in the "
        "microseconds before idna.encode() is ever called; a multi-second result here "
        "means the guard fired too late, or not at all."
    )


def test_sec_25_the_length_guard_applies_before_idna_in_service_names_too() -> None:
    """The second call site. `normalise_service_names` also calls `idna.encode`."""
    import time

    payload = "٠" * 60_000
    started = time.perf_counter()
    with pytest.raises(ExternalInferenceBlockedError, match="Refused before IDNA"):
        normalise_service_names([payload])
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, f"took {elapsed:.3f}s; the guard should make this near-instant"


#: Two independent boundaries, kept independent in these cases on purpose. A single label
#: over 63 characters is *also* over the 253-character total the moment it is long enough
#: to matter for SEC-25, which made an earlier version of this test look like it was
#: checking the total-length limit when it was only ever exercising the per-label one.
#: Each case here isolates one boundary: the multi-label hosts stay under 63 per label
#: while varying the total, and the single-label hosts stay under 253 total while varying
#: the label.
_FOUR_LABELS_AT = lambda total_extra: (  # noqa: E731 - local helper, not worth a def
    "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * (58 + total_extra)
)

assert len(_FOUR_LABELS_AT(3)) == 253  # 63+1+63+1+63+1+61 — sanity, not a test in itself


@pytest.mark.parametrize(
    "host,should_be_refused_by_length",
    [
        # Total-length boundary, each label safely under 63 so only the total is on trial.
        (_FOUR_LABELS_AT(3), False),  # 253 total — RFC 1035's limit, must pass through
        (_FOUR_LABELS_AT(4), True),  # 254 total — one character over
        # Per-label boundary, comfortably under 253 total so only the label is on trial.
        ("a" * 63, False),  # exactly at the per-label limit
        ("a" * 64, True),  # one character over, single label
    ],
)
def test_the_length_guard_is_off_by_one_correct(
    host: str, should_be_refused_by_length: bool
) -> None:
    """RFC 1035's limits are inclusive. Getting the boundary wrong in either direction is
    either a functional regression (rejecting a legal hostname) or a reopened DoS window
    (a label one character inside the limit still being long enough to matter, if idna's
    own bound turns out to differ from RFC 1035's by one)."""
    decision = classify(f"http://{host}/v1")
    if should_be_refused_by_length:
        assert decision.rule == "host-too-long", (
            f"host of length {len(host)} (labels: {[len(p) for p in host.split('.')]}) "
            f"should have been refused by length; got rule={decision.rule!r}"
        )
    else:
        assert decision.rule != "host-too-long", (
            f"host of length {len(host)} (labels: {[len(p) for p in host.split('.')]}) "
            "is within RFC 1035's bounds and should not be refused by length"
        )


def test_a_host_at_the_length_boundary_that_is_otherwise_valid_is_not_penalised() -> None:
    """The guard must not be so blunt that it refuses a legitimate long-but-legal name."""
    declared = normalise_service_names(["a" * 63 + ".internal"])
    decision = classify(f"http://{'a' * 63}.internal:8000/v1", service_names=declared)
    assert decision.allowed is True
    assert decision.rule != "host-too-long"
