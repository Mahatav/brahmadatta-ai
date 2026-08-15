from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SLIDES = REPO_ROOT / "docs" / "10-competition" / "five-slide-submission-outline.md"
CLAIM_AUDIT = REPO_ROOT / ".project" / "evidence" / "d9-submission-claim-audit-2026-08-15.json"
ROSTER = REPO_ROOT / "docs" / "10-competition" / "finale-roster-plan.md"
FREEZE = REPO_ROOT / "docs" / "10-competition" / "code-freeze-readiness.md"
AUDIT_SCRIPT = REPO_ROOT / "infrastructure" / "scripts" / "finale-closure-audit.mjs"


def test_submission_claim_audit_closes_issue_58_without_gpu_overclaim() -> None:
    audit = json.loads(CLAIM_AUDIT.read_text(encoding="utf-8"))
    slide_text = SLIDES.read_text(encoding="utf-8")

    assert audit["issue"] == 58
    assert audit["status"] == "pass"
    assert all(status == "pass" for status in audit["acceptance"].values())
    assert "FastAPI" not in slide_text
    assert "Visible rented-GPU utilization" not in slide_text
    assert "Tier 3: designed escalation path only" in slide_text
    assert "not presented as live" in slide_text


def test_submission_outline_preserves_unmeasured_and_cut_disclosures() -> None:
    slide_text = SLIDES.read_text(encoding="utf-8")

    assert "not measured / cut" in slide_text
    assert "not claimed complete until #50 passes" in slide_text.lower()
    assert "not claimed complete until #57 records real timings" in slide_text.lower()
    assert ".project/evidence/d9-submission-claim-audit-2026-08-15.json" in slide_text


def test_finale_closure_docs_keep_unclosed_p0s_honest() -> None:
    roster_text = ROSTER.read_text(encoding="utf-8")
    freeze_text = FREEZE.read_text(encoding="utf-8")

    assert "Status | Proposed, blocked on CEO confirmation" in roster_text
    assert "Confirm the two co-presenters" in roster_text
    assert "Status | Blocked" in freeze_text
    for issue in ["#50", "#57", "#59"]:
        assert issue in freeze_text


def test_finale_closure_audit_script_records_closeability() -> None:
    script = AUDIT_SCRIPT.read_text(encoding="utf-8")

    assert "d9-finale-closure-readiness" in script
    assert "issue_50" in script
    assert "issue_57" in script
    assert "issue_59" in script
    assert "issue_60" in script
    assert "blocked until" in script
