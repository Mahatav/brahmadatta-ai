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
