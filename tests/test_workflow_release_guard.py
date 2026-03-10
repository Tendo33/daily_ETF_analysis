from __future__ import annotations

from pathlib import Path

import yaml

QUALITY_GATE_PATH = Path(".github/workflows/quality_gate.yml")
RELEASE_GUARD_PATH = Path(".github/workflows/release_guard.yml")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_quality_gate_workflow_exists_and_has_core_checks() -> None:
    assert QUALITY_GATE_PATH.exists()
    data = _load(QUALITY_GATE_PATH)
    steps = data["jobs"]["quality"]["steps"]
    names = [item.get("name", "") for item in steps]
    assert "Ruff lint" in names
    assert "Ruff format check" in names
    assert "Mypy" in names
    assert "Pytest" in names


def test_release_guard_contains_required_contracts() -> None:
    assert RELEASE_GUARD_PATH.exists()
    data = _load(RELEASE_GUARD_PATH)

    steps = data["jobs"]["guard"]["steps"]
    names = [item.get("name", "") for item in steps]

    assert "Quality gate" in names
    assert "Alembic migration probe" in names
    assert "Smoke run" in names
    assert "Rollback guide" in names

    alembic_step = next(
        item for item in steps if item.get("name") == "Alembic migration probe"
    )
    assert "alembic upgrade head" in str(alembic_step.get("run", ""))

    smoke_step = next(item for item in steps if item.get("name") == "Smoke run")
    smoke_script = str(smoke_step.get("run", ""))
    assert "run_daily_analysis.py" in smoke_script
    assert "--skip-notify" in smoke_script

    rollback_step = next(item for item in steps if item.get("name") == "Rollback guide")
    assert "phase4-runbook.md" in str(rollback_step.get("run", ""))
