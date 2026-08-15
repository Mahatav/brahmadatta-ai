from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / ".project" / "evidence" / "d8-security-checklist-2026-08-14.json"
CHECKLIST = REPO_ROOT / "docs" / "05-testing" / "46-security-testing-checklist.md"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCS_TO_SCAN = [
    REPO_ROOT / "docs" / "01-product" / "11-feature-list.md",
    REPO_ROOT / "docs" / "09-company" / "06-architecture-spec.md",
    REPO_ROOT / "docs" / "Brahmadatta-AI-Master-MVP-Documentation.md",
]


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_security_checklist_records_every_item() -> None:
    evidence = _evidence()

    assert evidence["issue"] == 53
    assert len(evidence["checks"]) == 12
    statuses = {row["item"]: row["status"] for row in evidence["checks"]}
    assert statuses["Target egress and resource limits are enforced"] == "pass-with-not-run"
    assert all(status in {"pass", "pass-with-not-run"} for status in statuses.values())


def test_security_checklist_records_required_acceptance_outputs() -> None:
    acceptance = _evidence()["explicit_acceptance_evidence"]

    assert acceptance["python_dependency_audit"]["result"] == "No known vulnerabilities found"
    assert "0 vulnerabilities" in acceptance["javascript_dependency_audit"]["result"]
    assert acceptance["secret_scan"]["result"].startswith("one intentional dummy token fixture")
    assert acceptance["finale_dynamic_egress"]["status"] == "not run"
    assert "DATABASE_URL" in acceptance["finale_dynamic_egress"]["reason"]


def test_ci_runs_python_and_js_dependency_audits() -> None:
    workflow = CI.read_text(encoding="utf-8")

    assert "dependency audit (Python + JS)" in workflow
    assert "pip-audit -r apps/control-api/requirements.txt -r apps/control-api/requirements-dev.txt" in workflow
    assert "npm audit --audit-level=moderate" in workflow
    assert "npm audit --prefix apps/command-center --audit-level=moderate" in workflow


def test_evidence_bundle_wording_is_not_overclaimed() -> None:
    required = "hash-manifested, tamper-evident"
    blocked_phrases = ["signed evidence", "signed-by-hash evidence", "tamper-proof"]

    for path in DOCS_TO_SCAN:
        text = path.read_text(encoding="utf-8")
        assert required in text, path
        lowered = text.lower()
        for phrase in blocked_phrases:
            assert phrase not in lowered, f"{path} still says {phrase!r}"


def test_checklist_links_to_run_record() -> None:
    checklist = CHECKLIST.read_text(encoding="utf-8")

    assert ".project/evidence/d8-security-checklist-2026-08-14.json" in checklist
    assert "finale-egress-evidence.sh" in checklist
