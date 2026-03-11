from __future__ import annotations

from pathlib import Path

import pytest

PHASE4 = Path("docs/operations/phase4-runbook.md")
PHASE3 = Path("docs/operations/phase3-runbook.md")


def test_phase4_runbook_sections_and_links() -> None:
    if not PHASE4.exists():
        pytest.skip("Phase4 runbook is not included in this checkout.")
    text = PHASE4.read_text(encoding="utf-8")

    assert "Alert Severity" in text
    assert "Fault Triage" in text
    assert "Rollback And Recovery" in text
    assert "On-call Checklist" in text

    assert "/api/metrics" in text
    assert "/api/v1/system/lifecycle/cleanup" in text
    assert "scripts/backup_db.py" in text
    assert "scripts/restore_db.py" in text
    assert "scripts/drill_recovery.py" in text
    assert ".github/workflows/release_guard.yml" in text


def test_phase3_runbook_links_to_phase4() -> None:
    if not PHASE3.exists():
        pytest.skip("Phase3 runbook is not included in this checkout.")
    text = PHASE3.read_text(encoding="utf-8")
    assert "docs/operations/phase4-runbook.md" in text
