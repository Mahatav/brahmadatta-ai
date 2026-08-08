"""Operator commands for the transcript store. One command, one answer.

The fallback ladder asks for two things this provides.

**Pre-flight item 3** — *"Resolve one #82 transcript by hash and confirm the schema version
matches."* That is `verify`.

**Rung 3's trigger** — *"Replay does not resolve a policy-passing candidate: transcript
absent, `transcript_sha256` mismatch, or schema-version mismatch. One command, one answer —
no time box needed."* That is `resolve`, and the three outcomes have three distinct exit
codes so the answer is unambiguous to a person who has been awake for thirty hours:

    0  resolved
    3  no transcript for this request          (absent)
    4  a transcript is present but unusable    (digest or schema mismatch, ambiguity)
    5  the store or the arguments are wrong

Usage:

    python -m gateway.tools.transcripts_cli list   [--root DIR]
    python -m gateway.tools.transcripts_cli verify [--root DIR] [--sha256 DIGEST]
    python -m gateway.tools.transcripts_cli resolve --prompt-file F --prompt-version V \\
                                                    [--root DIR]

`resolve` prints the provenance label the run would carry, which is the other reason to run
it at pre-flight: the operator sees the exact sentence the UI will show before anybody is
watching.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gateway.errors import GatewayError, TranscriptError, TranscriptNotFoundError
from gateway.provenance import describe
from gateway.schemas import RESPONSE_SCHEMA_VERSION, GenerationRequest
from gateway.settings import DEFAULT_TRANSCRIPT_ROOT
from gateway.transcripts import TranscriptStore

EXIT_OK = 0
EXIT_ABSENT = 3
EXIT_UNUSABLE = 4
EXIT_BAD_INPUT = 5


def _store(args: argparse.Namespace) -> TranscriptStore:
    return TranscriptStore(Path(args.root), allow_synthetic=args.allow_synthetic)


def _cmd_list(args: argparse.Namespace) -> int:
    store = _store(args)
    paths = store.paths()
    if not paths:
        print(f"no transcripts in {store.root}")
        return EXIT_ABSENT

    print(f"{len(paths)} transcript(s) in {store.root}\n")
    for path in paths:
        try:
            transcript = store.load(path.stem)
        except TranscriptError as exc:
            print(f"  [UNUSABLE] {path.name}\n             {exc}")
            continue
        print(
            f"  [{transcript.capture_kind.value}] {path.stem[:16]}…\n"
            f"      captured   {transcript.captured_at.isoformat()}\n"
            f"      model      {transcript.model_name} "
            f"(artifact {transcript.model_artifact_sha256[:16]}…)\n"
            f"      prompt     {transcript.prompt_version}\n"
            f"      schema     {transcript.response_schema_version}\n"
            f"      note       {transcript.note or '—'}"
        )
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    """Re-hash every transcript and check its schema version. Pre-flight item 3."""
    store = _store(args)
    digests = [args.sha256] if args.sha256 else [p.stem for p in store.paths()]
    if not digests:
        print(f"no transcripts in {store.root}")
        return EXIT_ABSENT

    bad = 0
    for digest in digests:
        try:
            transcript = store.load(digest)
        except TranscriptNotFoundError as exc:
            print(f"[ABSENT]   {digest}\n           {exc}")
            bad += 1
            continue
        except TranscriptError as exc:
            print(f"[UNUSABLE] {digest}\n           {exc}")
            bad += 1
            continue

        matches = transcript.response_schema_version == RESPONSE_SCHEMA_VERSION
        marker = "[ok]" if matches else "[SCHEMA]"
        print(
            f"{marker:10s} {digest}\n"
            f"           digest recomputed and matches the filename\n"
            f"           schema {transcript.response_schema_version!r} "
            f"vs this build {RESPONSE_SCHEMA_VERSION!r}"
        )
        if not matches:
            bad += 1

    print(f"\n{len(digests) - bad} usable, {bad} not")
    return EXIT_OK if bad == 0 else EXIT_UNUSABLE


def _cmd_resolve(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        request = GenerationRequest(
            mission_id=args.mission_id,
            prompt=Path(args.prompt_file).read_text(encoding="utf-8"),
            prompt_version=args.prompt_version,
        )
    except OSError as exc:
        print(f"cannot read the prompt file: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT

    try:
        transcript = store.find(request)
    except TranscriptNotFoundError as exc:
        print(f"ABSENT — {exc}")
        return EXIT_ABSENT
    except TranscriptError as exc:
        print(f"UNUSABLE — {exc}")
        return EXIT_UNUSABLE

    # Build the provenance the run would carry, so the operator reads the real sentence
    # rather than a description of it.
    from gateway.backends import ReplaySource

    result = ReplaySource(store).produce(request)
    print(
        f"RESOLVED\n"
        f"  transcript   {transcript.digest()}\n"
        f"  captured     {transcript.captured_at.isoformat()}\n"
        f"  model        {transcript.model_name}\n"
        f"  artifact     {transcript.model_artifact_sha256}\n"
        f"  prompt       {transcript.prompt_version}\n"
        f"  schema       {transcript.response_schema_version}\n"
        f"  touched      {', '.join(result.candidate.touched_files) or '—'}\n"
        f"\n  the run will display: {describe(result.provenance)}"
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcripts", description="Inspect and resolve recorded model transcripts."
    )
    parser.add_argument("--root", default=str(DEFAULT_TRANSCRIPT_ROOT))
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="also read SYNTHETIC_FIXTURE transcripts, which are not model output and "
        "cannot be served as such",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list the store")

    verify = sub.add_parser("verify", help="re-hash and check schema versions")
    verify.add_argument("--sha256", default="", help="verify one transcript only")

    resolve = sub.add_parser("resolve", help="find the transcript for a prompt")
    resolve.add_argument("--prompt-file", required=True)
    resolve.add_argument("--prompt-version", required=True)
    resolve.add_argument("--mission-id", default="preflight")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = {"list": _cmd_list, "verify": _cmd_verify, "resolve": _cmd_resolve}[args.command]
    try:
        return handler(args)
    except GatewayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNUSABLE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
