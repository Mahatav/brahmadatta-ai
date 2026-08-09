"""No code path may reach a hosted third-party inference API.

The policy is allowlist-shaped, so the important assertions are the ones about hosts
nobody thought to add to a denylist.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from contracts.checks import MODEL_ENDPOINT_CHECK_ID, check_model_endpoints
from contracts.errors import ExternalInferenceBlockedError
from contracts.model_policy import (
    assert_local_inference_endpoint,
    is_local_inference_endpoint,
)

ALLOWED = [
    "http://127.0.0.1:8000/v1",
    "http://localhost:8000/v1",
    "http://[::1]:8000/v1",
    "http://10.0.0.5:8000/v1",
    "http://192.168.1.20:8000/v1",
    "http://172.16.4.4:8000/v1",
    "http://small-model.internal:8000/v1",
    "http://model-host.local:8000/v1",
    "https://model.svc.cluster.local/v1",
    # Reserved documentation range: not globally routable, so it cannot address a
    # hosted provider.
    "https://198.51.100.7/v1",
]

BLOCKED = [
    "https://api.openai.com/v1",
    "https://api.anthropic.com/v1",
    "https://generativelanguage.googleapis.com/v1beta",
    "https://openrouter.ai/api/v1",
    "https://api-inference.huggingface.co/models/x",
    "https://my-resource.openai.azure.com/openai",
    "https://bedrock-runtime.us-east-1.amazonaws.com",
    # Not on any denylist — blocked because it is simply a public host.
    "https://inference.some-startup.example.com/v1",
    "http://8.8.8.8:8000/v1",
    "https://51.15.20.30/v1",
    "ftp://small-model.internal/v1",
    "",
]


@pytest.mark.parametrize("url", ALLOWED)
def test_local_endpoints_are_permitted(url: str):
    assert is_local_inference_endpoint(url) is True
    assert_local_inference_endpoint("SMALL_MODEL_BASE_URL", url)


@override_settings(MODEL_SERVICE_NAMES=frozenset({"small-model"}))
def test_declared_compose_service_name_is_permitted():
    assert is_local_inference_endpoint("http://small-model:8000/v1") is True


@override_settings(MODEL_SERVICE_NAMES=frozenset())
def test_undeclared_bare_name_is_refused():
    assert is_local_inference_endpoint("http://small-model:8000/v1") is False


@pytest.mark.parametrize("url", BLOCKED)
def test_external_endpoints_are_blocked(url: str):
    assert is_local_inference_endpoint(url) is False
    with pytest.raises(ExternalInferenceBlockedError):
        assert_local_inference_endpoint("SMALL_MODEL_BASE_URL", url)


def test_subdomain_of_a_hosted_provider_is_blocked():
    assert is_local_inference_endpoint("https://eu.api.openai.com/v1") is False


def test_lookalike_internal_suffix_on_a_public_domain_is_blocked():
    assert is_local_inference_endpoint("https://api.openai.com.evil.example/v1") is False


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://api.openai.com/v1", False),
        ("http://127.0.0.1:8080/v1", True),
        ("http://169.254.169.254/", False),
        ("http://[fd00:ec2::254]/latest/meta-data/", False),
        ("http://metadata.google.internal/computeMetadata/v1/", False),
        ("http://100.100.100.200/latest/meta-data/", False),
        ("http://metadata.internal/", False),
        ("http://openai/v1", False),
        ("http://api。openai。com/v1", False),
        ("http://API.OPENAI.COM/v1", False),
        ("https://api.openai.com./v1", False),
        ("https://my-llm-proxy.internal/v1", True),
        ("http://[::ffff:169.254.169.254]/", False),
        ("http://[fe80::1]/", False),
        ("http://0.0.0.0/", False),
    ],
)
@override_settings(MODEL_SERVICE_NAMES=frozenset())
def test_sec_02_executed_proof_table(url: str, allowed: bool):
    assert is_local_inference_endpoint(url) is allowed


@override_settings(MODEL_ENDPOINTS={"SMALL_MODEL_BASE_URL": "https://api.openai.com/v1"})
def test_django_startup_check_fails_on_a_hosted_endpoint():
    messages = check_model_endpoints(None)
    assert [m.id for m in messages] == [MODEL_ENDPOINT_CHECK_ID]
    assert messages[0].is_serious()


@override_settings(
    MODEL_ENDPOINTS={"SMALL_MODEL_BASE_URL": "http://small-model.internal:8000/v1"}
)
def test_django_startup_check_passes_on_a_local_endpoint():
    assert check_model_endpoints(None) == []


@override_settings(MODEL_ENDPOINTS={"SMALL_MODEL_BASE_URL": "", "TIER3_BASE_URL": ""})
def test_unset_endpoints_are_not_an_error():
    """Tier 3 is cut; an empty variable must not fail startup."""
    assert check_model_endpoints(None) == []
