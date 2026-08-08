"""String-for-string equality against the contracts this adapter has to agree with.

Each of these mirrors a value defined in `apps/control-api/contracts/enums.py` rather than
importing it — this package does not depend on Django/pydantic (see the D-026 boundary
note in `workers/baseline/run.py`). That means the mirror can drift silently unless
something asserts equality against the real source; that is this file's only job.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENUMS_PATH = REPO_ROOT / "apps" / "control-api" / "contracts" / "enums.py"

pytestmark = pytest.mark.skipif(
    not ENUMS_PATH.is_file(),
    reason="apps/control-api/contracts/enums.py not present in this checkout",
)


def _enum_values(class_name: str) -> dict[str, str]:
    """Extract `NAME = "VALUE"` assignments from one class body, via the AST — never by
    importing the module, which would require a Django settings context this package must
    not depend on."""
    tree = ast.parse(ENUMS_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            values: dict[str, str] = {}
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    values[stmt.targets[0].id] = stmt.value.value
            return values
    raise AssertionError(f"class {class_name} not found in {ENUMS_PATH}")


def test_build_system_matches_language_adapter() -> None:
    from adapters.cpp.detect import BuildSystem

    contract_values = set(_enum_values("LanguageAdapter").values())
    adapter_values = {member.value for member in BuildSystem}
    assert adapter_values == contract_values


def test_isolation_mode_matches_contract() -> None:
    from adapters.cpp.jail import ISOLATION_MODE

    contract_values = set(_enum_values("IsolationMode").values())
    assert ISOLATION_MODE in contract_values


def test_baseline_event_types_match_contract() -> None:
    from workers.baseline.run import (
        _EVENT_BASELINE_FAILED,
        _EVENT_BASELINE_PASSED,
        _EVENT_BASELINE_RECORDED,
    )

    contract_values = set(_enum_values("EventType").values())
    assert _EVENT_BASELINE_RECORDED in contract_values
    assert _EVENT_BASELINE_PASSED in contract_values
    assert _EVENT_BASELINE_FAILED in contract_values
    # The literal string the D3 gate is checked against
    # (docs/09-company/01-vision-and-p0-cut.md §4) — pinned exactly, not just "present".
    assert _EVENT_BASELINE_PASSED == "BASELINE_PASSED"


def test_analyzer_tool_names_used_by_variants_match_contract() -> None:
    from adapters.cpp.variants import Variant, spec_for

    contract_values = set(_enum_values("AnalyzerTool").values())
    for variant in Variant:
        for tool in spec_for(variant).analyzer_tools:
            assert tool in contract_values, (
                f"{tool!r} from Variant.{variant.name} is not a real AnalyzerTool"
            )


def test_baseline_outcome_field_names_match_baseline_report_schema() -> None:
    """`BaselineOutcome` promises its field names line up with
    `contracts.schemas.evidence.BaselineReport` so `BaselineReport(**outcome.as_dict())`
    needs no translation layer. This test is the thing making that promise true rather
    than aspirational — it parses the real Pydantic model's field names via AST (same
    reasoning as `_enum_values`: no Django import) and diffs them against the dataclass."""
    import dataclasses

    from workers.baseline.run import BaselineOutcome

    schema_path = REPO_ROOT / "apps" / "control-api" / "contracts" / "schemas" / "evidence.py"
    if not schema_path.is_file():
        pytest.skip("contracts/schemas/evidence.py not present in this checkout")

    tree = ast.parse(schema_path.read_text(encoding="utf-8"))
    schema_fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BaselineReport":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    schema_fields.add(stmt.target.id)
            break
    else:
        raise AssertionError("BaselineReport not found in contracts/schemas/evidence.py")

    outcome_fields = {f.name for f in dataclasses.fields(BaselineOutcome)}
    # BaselineOutcome carries extra fields the contract type does not (snapshot,
    # isolation_mode, failure) — that is fine, it is a superset used to build the
    # eventual contract object. What must hold is that every REQUIRED schema field is
    # satisfiable directly from an outcome field of the same name.
    missing = (
        schema_fields - outcome_fields - {"log_ref"}
    )  # log_ref is Optional[ArtifactRef]; adapted, not copied
    assert not missing, f"BaselineOutcome is missing fields BaselineReport requires: {missing}"
