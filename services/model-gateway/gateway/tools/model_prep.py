"""Issue #73 model-prep evidence commands.

This is not a downloader. The multi-GB fetch and quantization run are explicit operator
actions; this command records the evidence around them and provides a tiny deterministic
backend for CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin

from gateway.client import get_json, iter_response_lines
from gateway.endpoint_policy import assert_local_inference_endpoint, classify
from gateway.errors import ExternalInferenceBlockedError, GatewayError
from gateway.ollama import (
    CODELLAMA_REVISION,
    DEFAULT_CODELLAMA_MODEL,
    DEFAULT_OLLAMA_ENDPOINT,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    OllamaCodeLlamaBackend,
    patch_candidate_from_model_text,
)
from gateway.schemas import (
    RESPONSE_SCHEMA_VERSION,
    GenerationRequest,
    PatchCandidate,
    sha256_of,
)
from gateway.service import build_gateway
from gateway.settings import GatewayMode, GatewaySettings

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_BAD_INPUT = 5
EVIDENCE_SCHEMA_VERSION = "model-prep/1"
DEFAULT_PATCH_PROMPT = (
    "Given this C parser crash and the minimized reproducer, propose the smallest safe "
    "unified diff. Return a patch candidate only."
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _host_memory_bytes() -> int | None:
    try:
        return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return None


def _hardware_snapshot() -> dict[str, object]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _host_memory_bytes(),
    }


def _write_json(payload: dict[str, object], output: str) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    if output == "-":
        print(text)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {path}")


def _service_names(args: argparse.Namespace) -> list[str]:
    return [name.strip() for raw in args.service_name for name in raw.split(",") if name.strip()]


def _bearer_token(args: argparse.Namespace) -> str:
    """D-075 / SEC-50. `--bearer-token`, defaulted from `MODEL_HOST_BEARER_TOKEN` in
    the environment so an operator running this against the compose `model-host-auth`
    sidecar (`--endpoint http://model-host:11434` or similar, from inside the
    `backend` network) does not have to repeat the value on every invocation. Blank is
    fine for the loopback `ollama serve` shape this tool's own defaults assume — that
    target has no auth of any kind to send.
    """
    explicit = getattr(args, "bearer_token", None)
    if explicit:
        return explicit
    return os.environ.get("MODEL_HOST_BEARER_TOKEN", "")


def _local_endpoint_record(endpoint: str, service_names: list[str]) -> dict[str, object]:
    decision = classify(endpoint, service_names=service_names)
    assert_local_inference_endpoint("MODEL_ENDPOINT", endpoint, service_names=service_names)
    return {
        "endpoint": endpoint,
        "local_only": True,
        "policy_rule": decision.rule,
        "policy_reason": decision.reason,
        "service_names": sorted(service_names),
    }


class FakeMeasuredBackend:
    """A deterministic stand-in for a local CPU-served model."""

    model_name = "fake-local-code-model"
    model_revision = "test"
    model_artifact_sha256 = "b" * 64
    served_from = "http://127.0.0.1:8080/v1"

    def __init__(self, *, wall_time_ms: int, output_tokens: int) -> None:
        self.wall_time_ms = wall_time_ms
        self.output_tokens = output_tokens

    def generate(self, request: GenerationRequest) -> tuple[PatchCandidate, int, int | None]:
        return (
            PatchCandidate(
                diff=(
                    "--- a/src/parse.c\n"
                    "+++ b/src/parse.c\n"
                    "@@ -118,7 +118,7 @@\n"
                    "-    while (cursor < end) {\n"
                    "+    while (cursor + 1 < end) {\n"
                ),
                rationale="Off-by-one on the terminating byte.",
                touched_files=("src/parse.c",),
                confidence=0.61,
            ),
            self.wall_time_ms,
            self.output_tokens,
        )


def _request_from_args(args: argparse.Namespace) -> GenerationRequest:
    prompt = (
        Path(args.prompt_file).read_text(encoding="utf-8")
        if args.prompt_file
        else DEFAULT_PATCH_PROMPT
    )
    return GenerationRequest(
        mission_id=args.mission_id,
        prompt=prompt,
        prompt_version=args.prompt_version,
        max_output_tokens=args.max_output_tokens,
        temperature=args.temperature,
        seed=args.seed,
    )


def _artifact_payload(args: argparse.Namespace) -> dict[str, object]:
    artifact = Path(args.artifact)
    if not artifact.is_file():
        raise FileNotFoundError(f"{artifact} is not a file")
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": "model-artifact-manifest",
        "recorded_at": _now(),
        "model": {
            "name": args.model_name,
            "revision": args.revision,
            "quantization": args.quantization,
        },
        "artifact": {
            "path": str(artifact),
            "bytes": artifact.stat().st_size,
            "sha256": _sha256_file(artifact),
        },
        "hardware": _hardware_snapshot(),
    }


def _fake_measure(args: argparse.Namespace) -> dict[str, object]:
    service_names = _service_names(args)
    request = _request_from_args(args)
    backend = FakeMeasuredBackend(
        wall_time_ms=args.fake_wall_time_ms,
        output_tokens=args.fake_output_tokens,
    )
    settings = GatewaySettings(
        mode=GatewayMode.LIVE,
        endpoint=args.endpoint,
        service_names=frozenset(service_names),
        resolve_endpoint=False,
    ).validate()
    started = time.perf_counter_ns()
    response = build_gateway(settings, live_backend=backend).generate(request)
    gateway_wall_time_ms = int((time.perf_counter_ns() - started) / 1_000_000)
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": "model-measurement",
        "recorded_at": _now(),
        "backend": "fake",
        "serving": _local_endpoint_record(args.endpoint, service_names),
        "model": {
            "name": backend.model_name,
            "revision": backend.model_revision,
            "artifact_sha256": backend.model_artifact_sha256,
        },
        "prompt": {
            "prompt_version": request.prompt_version,
            "prompt_sha256": request.prompt_sha256,
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "seed": request.seed,
        },
        "measurement": {
            "cold_start_ms": args.fake_cold_start_ms,
            "first_token_ms": args.fake_first_token_ms,
            "wall_time_ms": response.wall_time_ms,
            "gateway_wall_time_ms": gateway_wall_time_ms,
            "output_tokens": response.output_tokens,
            "throughput_tokens_per_sec": round(
                (response.output_tokens or 0) / (response.wall_time_ms / 1000), 3
            ),
            "sample_count": 1,
            "mode": "deterministic fake backend; no model was loaded",
        },
        "hardware": _hardware_snapshot(),
    }


def _delta_text(event: dict[str, Any]) -> str:
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    delta = choices[0].get("delta")
    if isinstance(delta, dict) and isinstance(delta.get("content"), str):
        return delta["content"]
    text = choices[0].get("text")
    return text if isinstance(text, str) else ""


def _ollama_delta_text(event: dict[str, Any]) -> str:
    message = event.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    response = event.get("response")
    return response if isinstance(response, str) else ""


def _stream_openai_compatible(args: argparse.Namespace) -> dict[str, object]:
    service_names = _service_names(args)
    request = _request_from_args(args)
    url = urljoin(args.endpoint.rstrip("/") + "/", "chat/completions")
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": request.prompt}],
        "temperature": request.temperature,
        "max_tokens": request.max_output_tokens,
        "stream": True,
    }
    started = time.perf_counter_ns()
    first_token_ms: int | None = None
    chunks = 0
    observed_chars = 0
    for line in iter_response_lines(url, payload, args.timeout_sec, bearer_token=_bearer_token(args)):
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            break
        try:
            text = _delta_text(json.loads(data))
        except json.JSONDecodeError:
            continue
        if not text:
            continue
        if first_token_ms is None:
            first_token_ms = int((time.perf_counter_ns() - started) / 1_000_000)
        chunks += 1
        observed_chars += len(text)
    wall_time_ms = int((time.perf_counter_ns() - started) / 1_000_000)
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": "model-measurement",
        "recorded_at": _now(),
        "backend": "openai-compatible-stream",
        "serving": _local_endpoint_record(args.endpoint, service_names),
        "model": {
            "name": args.model,
            "revision": args.revision,
            "artifact_sha256": args.artifact_sha256,
        },
        "prompt": {
            "prompt_version": request.prompt_version,
            "prompt_sha256": request.prompt_sha256,
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "seed": request.seed,
        },
        "measurement": {
            "cold_start_ms": None,
            "first_token_ms": first_token_ms,
            "wall_time_ms": wall_time_ms,
            "output_stream_chunks": chunks,
            "observed_output_chars": observed_chars,
            "throughput_stream_chunks_per_sec": round(chunks / (wall_time_ms / 1000), 3)
            if wall_time_ms
            else None,
            "sample_count": 1,
            "mode": "local OpenAI-compatible streaming endpoint",
        },
        "hardware": _hardware_snapshot(),
    }


def _stream_ollama(args: argparse.Namespace) -> dict[str, object]:
    service_names = _service_names(args)
    request = _request_from_args(args)
    url = urljoin(args.endpoint.rstrip("/") + "/", "chat")
    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON with keys diff, rationale, touched_files, "
                    "confidence. diff must be a unified diff."
                ),
            },
            {"role": "user", "content": request.prompt},
        ],
        "stream": True,
        "options": {
            "temperature": request.temperature,
            "num_predict": request.max_output_tokens,
        },
    }
    if request.seed is not None:
        payload["options"]["seed"] = request.seed

    started = time.perf_counter_ns()
    first_token_ms: int | None = None
    chunks = 0
    observed_chars = 0
    content_parts: list[str] = []
    final_event: dict[str, Any] = {}
    for line in iter_response_lines(url, payload, args.timeout_sec, bearer_token=_bearer_token(args)):
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        final_event = event if isinstance(event, dict) else final_event
        text = _ollama_delta_text(final_event)
        if not text:
            continue
        if first_token_ms is None:
            first_token_ms = int((time.perf_counter_ns() - started) / 1_000_000)
        chunks += 1
        observed_chars += len(text)
        content_parts.append(text)
    wall_time_ms = int((time.perf_counter_ns() - started) / 1_000_000)
    parsed_candidate = False
    parse_error = ""
    if content_parts:
        try:
            patch_candidate_from_model_text("".join(content_parts))
            parsed_candidate = True
        except GatewayError as exc:
            parse_error = str(exc)
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": "model-measurement",
        "recorded_at": _now(),
        "backend": "ollama-codellama-stream",
        "serving": _local_endpoint_record(args.endpoint, service_names),
        "model": {
            "name": args.model,
            "revision": args.revision,
            "artifact_sha256": args.artifact_sha256,
        },
        "prompt": {
            "prompt_version": request.prompt_version,
            "prompt_sha256": request.prompt_sha256,
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "seed": request.seed,
        },
        "measurement": {
            "cold_start_ms": None,
            "first_token_ms": first_token_ms,
            "wall_time_ms": wall_time_ms,
            "output_stream_chunks": chunks,
            "observed_output_chars": observed_chars,
            "throughput_stream_chunks_per_sec": round(chunks / (wall_time_ms / 1000), 3)
            if wall_time_ms
            else None,
            "ollama_eval_count": final_event.get("eval_count"),
            "ollama_eval_duration_ns": final_event.get("eval_duration"),
            "parsed_patch_candidate": parsed_candidate,
            "parse_error": parse_error,
            "sample_count": 1,
            "mode": "local Ollama CodeLlama streaming endpoint",
        },
        "hardware": _hardware_snapshot(),
    }


def _cmd_hash_artifact(args: argparse.Namespace) -> int:
    _write_json(_artifact_payload(args), args.output)
    return EXIT_OK


def _cmd_check_serving(args: argparse.Namespace) -> int:
    _write_json(
        {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "kind": "model-serving-boundary",
            "recorded_at": _now(),
            "serving": _local_endpoint_record(args.endpoint, _service_names(args)),
        },
        args.output,
    )
    return EXIT_OK


def _cmd_measure(args: argparse.Namespace) -> int:
    payload = (
        _fake_measure(args)
        if args.backend == "fake"
        else _stream_ollama(args)
        if args.backend == "ollama"
        else _stream_openai_compatible(args)
    )
    _write_json(payload, args.output)
    return EXIT_OK


def _cmd_attempts(args: argparse.Namespace) -> int:
    service_names = _service_names(args)
    request = _request_from_args(args)
    threshold = args.success_threshold
    attempts: list[dict[str, object]] = []
    successes = 0

    if args.backend == "ollama":
        backend = OllamaCodeLlamaBackend(
            endpoint=args.endpoint,
            model_name=args.model,
            model_revision=args.revision,
            model_artifact_sha256=args.artifact_sha256,
            timeout_sec=args.timeout_sec,
            bearer_token=_bearer_token(args),
        )
    else:
        backend = FakeMeasuredBackend(
            wall_time_ms=args.fake_wall_time_ms,
            output_tokens=args.fake_output_tokens,
        )

    for index in range(1, args.attempts + 1):
        attempt_seed = None if request.seed is None else request.seed + index - 1
        attempt_request = request.model_copy(update={"seed": attempt_seed})
        started = time.perf_counter_ns()
        try:
            candidate, wall_time_ms, output_tokens = backend.generate(attempt_request)
            policy_status = "SCHEMA_VALID"
            success = True
            error = ""
        except GatewayError as exc:
            candidate = None
            wall_time_ms = int((time.perf_counter_ns() - started) / 1_000_000)
            output_tokens = None
            policy_status = "REJECTED_BY_SCHEMA"
            success = False
            error = str(exc)

        if success:
            successes += 1

        attempts.append(
            {
                "attempt": index,
                "seed": attempt_seed,
                "success": success,
                "policy_status": policy_status,
                "compile_status": "NOT_RUN",
                "compile_detail": (
                    "This command records live model schema/policy viability only; "
                    "the deterministic D6 gate matrix records compile/regression verdicts."
                ),
                "wall_time_ms": wall_time_ms,
                "output_tokens": output_tokens,
                "candidate_sha256": sha256_of(candidate.model_dump(mode="json"))
                if candidate is not None
                else "",
                "touched_files": list(candidate.touched_files)
                if candidate is not None
                else [],
                "error": error,
            }
        )

    passed = successes >= threshold
    payload = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": "model-generation-attempts",
        "recorded_at": _now(),
        "backend": args.backend,
        "serving": _local_endpoint_record(args.endpoint, service_names),
        "model": {
            "name": args.model if args.backend == "ollama" else backend.model_name,
            "revision": args.revision if args.backend == "ollama" else backend.model_revision,
            "artifact_sha256": args.artifact_sha256
            if args.backend == "ollama"
            else backend.model_artifact_sha256,
        },
        "prompt": {
            "prompt_version": request.prompt_version,
            "prompt_sha256": request.prompt_sha256,
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "seed": request.seed,
        },
        "gate": {
            "required_attempts": args.attempts,
            "success_threshold": threshold,
            "schema_valid_successes": successes,
            "passed": passed,
            "status": (
                f"{successes} of {args.attempts} attempts returned schema-valid patch candidates"
            ),
        },
        "attempts": attempts,
        "hardware": _hardware_snapshot(),
    }
    _write_json(payload, args.output)
    return EXIT_OK if passed else EXIT_BLOCKED


#: #298: a real capacity refusal from Ollama ("model requires more system memory
#: (8.4 GiB) than is available (7.7 GiB)") surfaced live as an opaque HTTP 500 deep
#: inside a mission's PATCH_GENERATE call — the worst possible place to learn about a
#: resource-sizing problem that has nothing to do with the target repository. `doctor`
#: is this repo's one existing "run this explicitly before you trust the model host"
#: command (see `_cmd_plan`'s own printed operator sequence, which already runs
#: `doctor` as step 2, before any mission), so this is the earliest point an operator
#: already has a habit of checking. `--check-memory` (opt-in, see its own help text)
#: adds a real minimal generation call here — the only way to trigger Ollama's own
#: memory check ahead of time, since Ollama does not expose "would this fit" as a
#: separate, side-effect-free query. Opt-in, not automatic, for the same reason this
#: module's own docstring gives for never pulling a model automatically: it is a real,
#: possibly slow (a cold model load costs ~60-190s, D-123) action with a real resource
#: cost, and an operator who only wants the fast reachability/presence checks above
#: should not pay for it by default.
_INSUFFICIENT_MEMORY_PROMPT = "Return the single word OK."


def _run_memory_check(args: argparse.Namespace) -> tuple[bool, str, dict[str, object]]:
    """Trigger Ollama's own memory-fit check for real, via the smallest live
    generation call this backend can make (`max_output_tokens=1`). Returns
    `(fits, message, details)`. `fits=False` covers both a confirmed capacity refusal
    and any other failure of this specific call — either way, the operator should not
    proceed to trust `--check-memory`'s absence of a problem when it never actually
    ran the check to completion.
    """
    backend = OllamaCodeLlamaBackend(
        endpoint=args.endpoint,
        model_name=args.model,
        model_revision=args.revision,
        model_artifact_sha256=args.artifact_sha256,
        timeout_sec=args.memory_check_timeout_sec,
        bearer_token=_bearer_token(args),
    )
    request = GenerationRequest(
        mission_id="model-prep-doctor-memory-check",
        prompt=_INSUFFICIENT_MEMORY_PROMPT,
        prompt_version="patch-prompt/3",
        max_output_tokens=1,
    )
    try:
        backend.generate(request)
    except GatewayError as exc:
        return False, str(exc), dict(exc.details)
    return True, f"{args.model} loaded and generated inside the configured memory limit", {}


def _cmd_doctor(args: argparse.Namespace) -> int:
    service_names = _service_names(args)
    payload: dict[str, object] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": "ollama-codellama-doctor",
        "recorded_at": _now(),
        "backend": "ollama",
        "model": {
            "name": args.model,
            "revision": args.revision,
            "artifact_sha256": args.artifact_sha256,
        },
        "serving": _local_endpoint_record(args.endpoint, service_names),
        "checks": {
            "endpoint_reachable": False,
            "model_present": False,
            "schema_probe_passed": False,
            # `None` = not checked (the default; see `--check-memory`'s help text),
            # distinct from `True`/`False` = checked and passed/failed.
            "model_fits_memory": None,
        },
        "status": "unreachable",
        "message": "",
        "degraded_state": {
            "active": True,
            "tier": "deterministic",
            "reason": "local CodeLlama is not proven reachable",
        },
        "hardware": _hardware_snapshot(),
    }
    try:
        tags = get_json(
            urljoin(args.endpoint.rstrip("/") + "/", "tags"),
            args.timeout_sec,
            bearer_token=_bearer_token(args),
        )
    except (GatewayError, OSError, URLError) as exc:
        payload["message"] = str(exc)
        _write_json(payload, args.output)
        return EXIT_BLOCKED

    models = _ollama_model_names(tags)
    present = args.model in models
    payload["checks"] = {
        "endpoint_reachable": True,
        "model_present": present,
        "schema_probe_passed": False,
        "model_fits_memory": None,
    }
    payload["ollama_models"] = models
    if not present:
        payload["status"] = "model-missing"
        payload["message"] = f"{args.model} is not present in the local Ollama store"
        _write_json(payload, args.output)
        return EXIT_BLOCKED

    if args.check_memory:
        fits, message, details = _run_memory_check(args)
        payload["checks"]["model_fits_memory"] = fits
        if not fits:
            payload["status"] = "insufficient-memory"
            payload["message"] = message
            payload["memory_check_detail"] = details
            payload["degraded_state"] = {
                "active": True,
                "tier": "deterministic",
                "reason": f"{args.model} does not fit in the model-host container's "
                "actual memory — see 'message' and 'memory_check_detail' for the "
                "specific amounts and what to check (MODEL_HOST_MEM_LIMIT vs. the "
                "model's real requirement).",
            }
            _write_json(payload, args.output)
            return EXIT_BLOCKED

    payload["status"] = "ready"
    payload["message"] = f"{args.model} is present on the local Ollama endpoint"
    if args.check_memory:
        payload["message"] += " and fits in the model-host container's actual memory"
    payload["degraded_state"] = {
        "active": False,
        "tier": "local-codellama",
        "reason": "",
    }
    _write_json(payload, args.output)
    return EXIT_OK


def _cmd_plan(args: argparse.Namespace) -> int:
    root = args.evidence_dir.rstrip("/")
    print(
        "\n".join(
            [
                "# Issue #73 operator command shape",
                "",
                "No command below fetches a model unless the operator runs it explicitly.",
                "",
                "1. Fetch the chosen CodeLlama model into Ollama's local store:",
                f"   ollama pull {DEFAULT_CODELLAMA_MODEL}",
                "",
                "2. Serve locally only, then prove the endpoint boundary:",
                "   ollama serve  # default API: http://127.0.0.1:11434/api",
                "   python -m gateway.tools.model_prep doctor "
                f"--endpoint {DEFAULT_OLLAMA_ENDPOINT} --output {root}/model-doctor.json",
                "   python -m gateway.tools.model_prep check-serving --endpoint "
                f"{DEFAULT_OLLAMA_ENDPOINT} --output {root}/model-serving.json",
                "",
                "2b. #298: before trusting this model host for a real mission (a demo,",
                "    a competition run — anything where a mid-mission model failure is",
                "    expensive to discover), also run doctor's real memory pre-flight.",
                "    This is the ONLY way to trigger Ollama's own memory check ahead of",
                "    time: it makes one real, minimal generation call, so it costs a cold",
                "    model load (~60-190s observed) and is not part of step 2's fast",
                "    reachability check by default.",
                "   python -m gateway.tools.model_prep doctor --check-memory "
                f"--endpoint {DEFAULT_OLLAMA_ENDPOINT} --output {root}/model-doctor.json",
                "    A clear, actionable 'insufficient-memory' status here (not a bare",
                "    HTTP 500 mid-mission) means the model needs more memory than",
                "    MODEL_HOST_MEM_LIMIT actually gives it on THIS machine — a capacity",
                "    decision for whoever owns the hardware this runs on, not something",
                "    this command can fix by itself.",
                "",
                "3. Measure first-token latency and schema-fit through local Ollama:",
                "   python -m gateway.tools.model_prep measure --backend ollama "
                f"--endpoint {DEFAULT_OLLAMA_ENDPOINT} --model {DEFAULT_CODELLAMA_MODEL} "
                f"--revision {CODELLAMA_REVISION} "
                f"--prompt-file prompts/patch-generation.txt --prompt-version patch-prompt/3 "
                f"--output {root}/model-measurement.json",
                "",
                "Optional GGUF artifact evidence for a manually managed model file:",
                f"   python -m gateway.tools.model_prep hash-artifact --artifact <model.gguf> "
                f"--model-name {DEFAULT_CODELLAMA_MODEL} --revision {CODELLAMA_REVISION} "
                f"--quantization <ollama-local> --output {root}/model-artifact.json",
                "",
                "Expected evidence files:",
                f"   {root}/model-serving.json",
                f"   {root}/model-measurement.json",
            ]
        )
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model-prep",
        description="Prepare #73 local model artifact and measurement evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    artifact = sub.add_parser("hash-artifact", help="record a model artifact hash manifest")
    artifact.add_argument("--artifact", required=True)
    artifact.add_argument("--model-name", required=True)
    artifact.add_argument("--revision", required=True)
    artifact.add_argument("--quantization", required=True)
    artifact.add_argument("--output", default="-")
    serving = sub.add_parser("check-serving", help="prove an inference endpoint is local-only")
    serving.add_argument("--endpoint", required=True)
    serving.add_argument("--service-name", action="append", default=[])
    serving.add_argument("--output", default="-")
    doctor = sub.add_parser("doctor", help="prove Ollama CodeLlama is local, reachable, and present")
    doctor.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT)
    doctor.add_argument("--service-name", action="append", default=[])
    doctor.add_argument("--model", default=DEFAULT_CODELLAMA_MODEL)
    doctor.add_argument("--revision", default=CODELLAMA_REVISION)
    doctor.add_argument("--artifact-sha256", default="")
    doctor.add_argument("--timeout-sec", type=float, default=5.0)
    doctor.add_argument("--output", default="-")
    # D-075 / SEC-50: required to reach the compose model-host-auth sidecar; not
    # required for a bare loopback `ollama serve`. Defaults from MODEL_HOST_BEARER_TOKEN.
    doctor.add_argument("--bearer-token", default=None)
    # #298: opt-in (see `_run_memory_check`'s comment for why this is not the
    # default) real generation call that forces Ollama to attempt loading the model
    # into memory, so a real capacity refusal ("model requires more system memory ...
    # than is available") is caught here — before a competition mission ever depends
    # on this model host — instead of mid-PATCH_GENERATE.
    doctor.add_argument(
        "--check-memory",
        action="store_true",
        help=(
            "Also make one real, minimal generation call to force Ollama's own "
            "memory check to run now. Off by default: unlike the checks above, this "
            "has a real cost (a cold model load, ~60-190s observed) and a real "
            "side effect (loads the model into memory). Run this explicitly before "
            "a competition mission depends on this model host, not on every routine "
            "reachability check."
        ),
    )
    doctor.add_argument(
        "--memory-check-timeout-sec",
        type=float,
        default=DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        help="Timeout for --check-memory's generation call, separate from "
        "--timeout-sec's fast reachability-check timeout above (default: "
        f"{DEFAULT_OLLAMA_TIMEOUT_SECONDS:.0f}s, matching the real PATCH_GENERATE "
        "call's own default so this check does not time out before a real cold "
        "model load would).",
    )
    measure = sub.add_parser("measure", help="measure local backend latency evidence")
    measure.add_argument("--backend", choices=["fake", "openai-compatible", "ollama"], required=True)
    measure.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT)
    measure.add_argument("--service-name", action="append", default=[])
    measure.add_argument("--output", default="-")
    measure.add_argument("--mission-id", default="model-prep")
    measure.add_argument("--prompt-file", default="")
    measure.add_argument("--prompt-version", default="patch-prompt/3")
    measure.add_argument("--max-output-tokens", type=int, default=1024)
    measure.add_argument("--temperature", type=float, default=0.0)
    measure.add_argument("--seed", type=int)
    measure.add_argument("--model", default=DEFAULT_CODELLAMA_MODEL)
    measure.add_argument("--revision", default=CODELLAMA_REVISION)
    measure.add_argument("--artifact-sha256", default="")
    measure.add_argument("--timeout-sec", type=float, default=300.0)
    measure.add_argument("--fake-cold-start-ms", type=int, default=0)
    measure.add_argument("--fake-first-token-ms", type=int, default=250)
    measure.add_argument("--fake-wall-time-ms", type=int, default=4200)
    measure.add_argument("--fake-output-tokens", type=int, default=128)
    # D-075 / SEC-50: see the matching --bearer-token comment on `doctor` above.
    measure.add_argument("--bearer-token", default=None)
    attempts = sub.add_parser("attempts", help="record D6 live model patch-generation attempts")
    attempts.add_argument("--backend", choices=["fake", "ollama"], required=True)
    attempts.add_argument("--attempts", type=int, default=10)
    attempts.add_argument("--success-threshold", type=int, default=3)
    attempts.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT)
    attempts.add_argument("--service-name", action="append", default=[])
    attempts.add_argument("--output", default="-")
    attempts.add_argument("--mission-id", default="d6-model-attempts")
    attempts.add_argument("--prompt-file", default="")
    attempts.add_argument("--prompt-version", default="patch-prompt/3")
    attempts.add_argument("--max-output-tokens", type=int, default=1024)
    attempts.add_argument("--temperature", type=float, default=0.0)
    attempts.add_argument("--seed", type=int)
    attempts.add_argument("--model", default=DEFAULT_CODELLAMA_MODEL)
    attempts.add_argument("--revision", default=CODELLAMA_REVISION)
    attempts.add_argument("--artifact-sha256", default="")
    attempts.add_argument("--timeout-sec", type=float, default=300.0)
    attempts.add_argument("--fake-wall-time-ms", type=int, default=4200)
    attempts.add_argument("--fake-output-tokens", type=int, default=128)
    # D-075 / SEC-50: see the matching --bearer-token comment on `doctor` above.
    attempts.add_argument("--bearer-token", default=None)
    plan = sub.add_parser("plan", help="print the real operator command shape")
    plan.add_argument("--evidence-dir", default="evidence/model-prep")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return {
            "hash-artifact": _cmd_hash_artifact,
            "check-serving": _cmd_check_serving,
            "doctor": _cmd_doctor,
            "measure": _cmd_measure,
            "attempts": _cmd_attempts,
            "plan": _cmd_plan,
        }[args.command](args)
    except ExternalInferenceBlockedError as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        return EXIT_BLOCKED
    except (GatewayError, OSError, URLError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT


def _ollama_model_names(payload: dict[str, Any]) -> list[str]:
    raw_models = payload.get("models", [])
    names: list[str] = []
    if not isinstance(raw_models, list):
        return names
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        for key in ("name", "model"):
            value = item.get(key)
            if isinstance(value, str) and value not in names:
                names.append(value)
    return sorted(names)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
