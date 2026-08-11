from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gateway.tools import model_prep


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_hash_artifact_records_size_and_sha256(tmp_path: Path) -> None:
    artifact = tmp_path / "tiny-model.gguf"
    artifact.write_bytes(b"not a real model; enough for a deterministic hash\n")
    output = tmp_path / "artifact.json"

    assert (
        model_prep.main(
            [
                "hash-artifact",
                "--artifact",
                str(artifact),
                "--model-name",
                "tiny-local-code-model",
                "--revision",
                "rev-1",
                "--quantization",
                "q4_K_M",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    payload = _load(output)
    assert payload["kind"] == "model-artifact-manifest"
    assert payload["schema_version"] == model_prep.EVIDENCE_SCHEMA_VERSION
    assert payload["model"] == {
        "name": "tiny-local-code-model",
        "revision": "rev-1",
        "quantization": "q4_K_M",
    }
    artifact_record = payload["artifact"]
    assert artifact_record["bytes"] == artifact.stat().st_size
    assert artifact_record["sha256"] == model_prep._sha256_file(artifact)


def test_check_serving_blocks_hosted_provider(tmp_path: Path, capsys: Any) -> None:
    output = tmp_path / "serving.json"

    assert (
        model_prep.main(
            [
                "check-serving",
                "--endpoint",
                "https://api.openai.com/v1",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_BLOCKED
    )

    captured = capsys.readouterr()
    assert "blocked:" in captured.err
    assert not output.exists()


def test_check_serving_records_local_policy_rule(tmp_path: Path) -> None:
    output = tmp_path / "serving.json"

    assert (
        model_prep.main(
            [
                "check-serving",
                "--endpoint",
                "http://127.0.0.1:8080/v1",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    serving = _load(output)["serving"]
    assert serving["local_only"] is True
    assert serving["policy_rule"] == "allowed-network"


def test_fake_measure_goes_through_gateway_and_emits_evidence(tmp_path: Path) -> None:
    output = tmp_path / "measurement.json"

    assert (
        model_prep.main(
            [
                "measure",
                "--backend",
                "fake",
                "--endpoint",
                "http://127.0.0.1:8080/v1",
                "--fake-cold-start-ms",
                "11",
                "--fake-first-token-ms",
                "222",
                "--fake-wall-time-ms",
                "4000",
                "--fake-output-tokens",
                "100",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    payload = _load(output)
    assert payload["kind"] == "model-measurement"
    assert payload["backend"] == "fake"
    measurement = payload["measurement"]
    assert measurement["cold_start_ms"] == 11
    assert measurement["first_token_ms"] == 222
    assert measurement["wall_time_ms"] == 4000
    assert measurement["output_tokens"] == 100
    assert measurement["throughput_tokens_per_sec"] == 25.0
    assert "no model was loaded" in str(measurement["mode"])
    assert payload["model"]["artifact_sha256"] == "b" * 64
    assert payload["prompt"]["response_schema_version"] == "patch-candidate/1"


def test_plan_prints_exact_operator_command_shape(capsys: Any) -> None:
    assert model_prep.main(["plan", "--evidence-dir", "evidence/d4-model"]) == 0

    captured = capsys.readouterr()
    assert "huggingface-cli download" in captured.out
    assert "llama-quantize" in captured.out
    assert "hash-artifact" in captured.out
    assert "check-serving" in captured.out
    assert "measure --backend openai-compatible" in captured.out
    assert "evidence/d4-model/model-measurement.json" in captured.out
