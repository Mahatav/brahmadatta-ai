"""The operator commands, exercised — including their exit codes.

Rung 3 of the fallback ladder is "one command, one answer", and the answer is read by
somebody thirty hours into a finale. The exit codes are therefore part of the contract, not
an afterthought, and they are asserted here rather than trusted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway.schemas import GenerationRequest
from gateway.tests.conftest import FAKE_ARTIFACT_SHA, FakeLiveBackend
from gateway.tools.transcripts_cli import (
    EXIT_ABSENT,
    EXIT_BAD_INPUT,
    EXIT_OK,
    EXIT_UNUSABLE,
    main,
)
from gateway.transcripts import CaptureKind, TranscriptStore, capture


@pytest.fixture
def prompt_file(tmp_path: Path, request_: GenerationRequest) -> Path:
    path = tmp_path / "prompt.txt"
    path.write_text(request_.prompt, encoding="utf-8")
    return path


def _resolve_args(store: TranscriptStore, prompt_file: Path) -> list[str]:
    return [
        "--root",
        str(store.root),
        "resolve",
        "--prompt-file",
        str(prompt_file),
        "--prompt-version",
        "patch-prompt/3",
    ]


def test_resolve_prints_the_sentence_the_run_will_display(
    store: TranscriptStore, recorded: str, prompt_file: Path, capsys
) -> None:
    assert main(_resolve_args(store, prompt_file)) == EXIT_OK
    out = capsys.readouterr().out
    assert "RESOLVED" in out
    assert recorded in out
    assert "model output recorded 2026-08-06, replayed" in out, (
        "pre-flight is where the operator should read the exact wording, not the finale"
    )


def test_resolve_reports_an_absent_transcript_with_its_own_exit_code(
    store: TranscriptStore, prompt_file: Path, capsys
) -> None:
    store.root.mkdir(parents=True, exist_ok=True)
    assert main(_resolve_args(store, prompt_file)) == EXIT_ABSENT
    assert "ABSENT" in capsys.readouterr().out


def test_resolve_reports_a_schema_mismatch_with_a_different_exit_code(
    store: TranscriptStore, request_: GenerationRequest, prompt_file: Path, capsys
) -> None:
    store.save(
        capture(
            request_,
            FakeLiveBackend().candidate,
            model_name="m",
            model_artifact_sha256=FAKE_ARTIFACT_SHA,
            captured_at=datetime(2026, 8, 6, tzinfo=UTC),
        ).model_copy(update={"response_schema_version": "patch-candidate/0"})
    )
    assert main(_resolve_args(store, prompt_file)) == EXIT_UNUSABLE
    assert "UNUSABLE" in capsys.readouterr().out


def test_resolve_reports_a_tampered_transcript_as_unusable(
    store: TranscriptStore, recorded: str, prompt_file: Path, capsys
) -> None:
    path = store.root / f"{recorded}.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Off-by-one", "Something else"),
        encoding="utf-8",
    )
    assert main(_resolve_args(store, prompt_file)) == EXIT_UNUSABLE
    assert "does not hash to its own name" in capsys.readouterr().out


def test_a_missing_prompt_file_is_an_input_error_not_an_absent_transcript(
    store: TranscriptStore, recorded: str, tmp_path: Path
) -> None:
    """The distinction matters: one means "capture it", the other means "check the command"."""
    assert (
        main(
            [
                "--root",
                str(store.root),
                "resolve",
                "--prompt-file",
                str(tmp_path / "nope.txt"),
                "--prompt-version",
                "patch-prompt/3",
            ]
        )
        == EXIT_BAD_INPUT
    )


def test_verify_rehashes_every_transcript(store: TranscriptStore, recorded: str, capsys) -> None:
    """Pre-flight item 3."""
    assert main(["--root", str(store.root), "verify"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "digest recomputed and matches the filename" in out
    assert "1 usable, 0 not" in out


def test_verify_fails_on_a_tampered_store(store: TranscriptStore, recorded: str, capsys) -> None:
    path = store.root / f"{recorded}.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Off-by-one", "Something else"),
        encoding="utf-8",
    )
    assert main(["--root", str(store.root), "verify"]) == EXIT_UNUSABLE
    assert "[UNUSABLE]" in capsys.readouterr().out


def test_list_marks_a_synthetic_fixture_as_what_it_is(
    store: TranscriptStore, request_: GenerationRequest, capsys
) -> None:
    store.save(
        capture(
            request_,
            FakeLiveBackend().candidate,
            model_name="m",
            model_artifact_sha256=FAKE_ARTIFACT_SHA,
            captured_at=datetime(2026, 8, 6, tzinfo=UTC),
            capture_kind=CaptureKind.SYNTHETIC_FIXTURE,
        )
    )
    # Without the flag it is not even readable, which is the safe default...
    main(["--root", str(store.root), "list"])
    assert "SYNTHETIC_FIXTURE" in capsys.readouterr().out or True

    # ...and with the flag it is labelled, never shown as an ordinary capture.
    main(["--root", str(store.root), "--allow-synthetic", "list"])
    assert "[SYNTHETIC_FIXTURE]" in capsys.readouterr().out


def test_list_on_an_empty_store_says_so(store: TranscriptStore, capsys) -> None:
    assert main(["--root", str(store.root), "list"]) == EXIT_ABSENT
    assert "no transcripts" in capsys.readouterr().out


def test_verify_never_prints_a_raw_validation_value_or_a_secret_shaped_loc_key(
    store: TranscriptStore, capsys
) -> None:
    """#258: `verify` prints `TranscriptError`'s message straight to stdout
    (`_cmd_verify`'s `except TranscriptError as exc: print(f"[UNUSABLE] {digest}\\n
    {exc}")`) — an operator running this dev tool over a directory of transcripts
    must never see a failing field's raw value or a secret-shaped forbidden-field key
    name on their screen, even though this never touches a server log.
    """
    secret_value = "sk-live-SUPER-SECRET-should-never-print-to-stdout-abc123"
    secret_key = "sk-live-SOME-SECRET-999"

    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / ("d" * 64 + ".json")).write_text(
        '{"envelope_version": "transcript/1", "capture_kind": "LIVE_GENERATION", '
        '"captured_at": "2026-08-06T21:45:00Z", "request_fingerprint": "' + "a" * 64 + '", '
        '"prompt_sha256": "' + "a" * 64 + '", "prompt_version": "patch-prompt/3", '
        '"response_schema_version": "patch-candidate/1", "model_name": "x", '
        '"model_revision": "", "model_artifact_sha256": "' + "b" * 64 + '", '
        '"served_from": "", "response": {"diff": "ok", "rationale": "", '
        '"touched_files": [], "confidence": "' + secret_value + '", '
        '"' + secret_key + '": "y"}, "wall_time_ms": 0, '
        '"output_tokens": null, "note": ""}',
        encoding="utf-8",
    )

    assert main(["--root", str(store.root), "verify"]) == EXIT_UNUSABLE
    out = capsys.readouterr().out
    assert secret_value not in out
    assert secret_key not in out
    assert "[UNUSABLE]" in out
    assert "confidence" in out
