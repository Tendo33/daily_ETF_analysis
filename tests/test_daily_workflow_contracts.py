from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/daily_etf_analysis.yml")


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_daily_workflow_dispatch_inputs_and_concurrency() -> None:
    data = _load_workflow()
    on_section = data.get("on")
    if on_section is None:
        on_section = data.get(True, {})
    dispatch = on_section["workflow_dispatch"]
    inputs = dispatch["inputs"]

    assert "force_run" in inputs
    assert "symbols" in inputs
    assert "market" in inputs
    assert "skip_notify" in inputs

    concurrency = data["concurrency"]
    assert "daily-etf-analysis" in concurrency["group"]
    assert concurrency["cancel-in-progress"] is False


def test_daily_workflow_probe_smoke_and_artifact_contract() -> None:
    data = _load_workflow()
    steps = data["jobs"]["analyze"]["steps"]
    names = [item.get("name", "") for item in steps]

    assert "Config probe (no secrets)" in names
    assert "Run daily analysis" in names
    assert "Run daily analysis smoke" in names
    assert "Upload artifacts" in names

    smoke_step = next(
        item for item in steps if item.get("name") == "Run daily analysis smoke"
    )
    run_script = str(smoke_step.get("run", ""))
    assert "--skip-notify" in run_script

    artifact_step = next(
        item for item in steps if item.get("name") == "Upload artifacts"
    )
    artifact_path = str(artifact_step.get("with", {}).get("path", ""))
    assert "reports/" in artifact_path
    assert "logs/" in artifact_path
