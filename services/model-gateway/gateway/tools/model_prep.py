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
from urllib.request import Request, urlopen

from gateway.endpoint_policy import assert_local_inference_endpoint, classify
from gateway.errors import ExternalInferenceBlockedError, GatewayError
from gateway.schemas import RESPONSE_SCHEMA_VERSION, GenerationRequest, PatchCandidate
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
    http_request = Request(  # noqa: S310 - endpoint was accepted by gateway policy above.
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(http_request, timeout=args.timeout_sec) as response:  # noqa: S310
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
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
    payload = _fake_measure(args) if args.backend == "fake" else _stream_openai_compatible(args)
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
                "1. Fetch the chosen model artifact into a local cache:",
                "   huggingface-cli download <repo/model> <file.gguf> "
                "--revision <pinned-revision> --local-dir .model-cache/<model>",
                "",
                "2. If the source is not already quantized, quantize locally:",
                "   ./llama.cpp/llama-quantize <source.gguf> <target-q4_k_m.gguf> q4_K_M",
                "",
                "3. Record the pinned artifact hash:",
                f"   python -m gateway.tools.model_prep hash-artifact --artifact "
                f".model-cache/<model>/<target-q4_k_m.gguf> --model-name <model> "
                f"--revision <pinned-revision> --quantization q4_K_M --output "
                f"{root}/model-artifact.json",
                "",
                "4. Serve locally only, then prove the endpoint boundary:",
                "   ./llama.cpp/llama-server -m .model-cache/<model>/<target-q4_k_m.gguf> "
                "--host 127.0.0.1 --port 8080",
                "   python -m gateway.tools.model_prep check-serving --endpoint "
                f"http://127.0.0.1:8080/v1 --output {root}/model-serving.json",
                "",
                "5. Measure first-token latency and throughput through the local endpoint:",
                "   python -m gateway.tools.model_prep measure --backend openai-compatible "
                "--endpoint http://127.0.0.1:8080/v1 --model <model> "
                "--revision <pinned-revision> --artifact-sha256 <sha256> "
                f"--prompt-file prompts/patch-generation.txt --prompt-version patch-prompt/3 "
                f"--output {root}/model-measurement.json",
                "",
                "Expected evidence files:",
                f"   {root}/model-artifact.json",
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
    measure = sub.add_parser("measure", help="measure local backend latency evidence")
    measure.add_argument("--backend", choices=["fake", "openai-compatible"], required=True)
    measure.add_argument("--endpoint", default="http://127.0.0.1:8080/v1")
    measure.add_argument("--service-name", action="append", default=[])
    measure.add_argument("--output", default="-")
    measure.add_argument("--mission-id", default="model-prep")
    measure.add_argument("--prompt-file", default="")
    measure.add_argument("--prompt-version", default="patch-prompt/3")
    measure.add_argument("--max-output-tokens", type=int, default=1024)
    measure.add_argument("--temperature", type=float, default=0.0)
    measure.add_argument("--seed", type=int)
    measure.add_argument("--model", default="local-code-model")
    measure.add_argument("--revision", default="")
    measure.add_argument("--artifact-sha256", default="")
    measure.add_argument("--timeout-sec", type=float, default=300.0)
    measure.add_argument("--fake-cold-start-ms", type=int, default=0)
    measure.add_argument("--fake-first-token-ms", type=int, default=250)
    measure.add_argument("--fake-wall-time-ms", type=int, default=4200)
    measure.add_argument("--fake-output-tokens", type=int, default=128)
    plan = sub.add_parser("plan", help="print the real operator command shape")
    plan.add_argument("--evidence-dir", default="evidence/model-prep")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return {
            "hash-artifact": _cmd_hash_artifact,
            "check-serving": _cmd_check_serving,
            "measure": _cmd_measure,
            "plan": _cmd_plan,
        }[args.command](args)
    except ExternalInferenceBlockedError as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        return EXIT_BLOCKED
    except (GatewayError, OSError, URLError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
