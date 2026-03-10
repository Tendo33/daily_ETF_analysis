from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.security_scan import scan_security


def test_security_scan_contract() -> None:
    payload = scan_security(root=Path("."))

    assert set(payload) == {
        "dependency_vulns",
        "secret_leaks",
        "policy_violations",
        "summary",
    }
    assert isinstance(payload["dependency_vulns"], list)
    assert isinstance(payload["secret_leaks"], list)
    assert isinstance(payload["policy_violations"], list)

    for key in ("dependency_vulns", "secret_leaks", "policy_violations"):
        for item in payload[key]:
            assert isinstance(item, dict)


def test_security_scan_exit_code_and_summary() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/security_scan.py", "--root", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)
    assert "summary" in payload
    assert set(payload["summary"]) == {
        "dependency_vulns",
        "secret_leaks",
        "policy_violations",
        "total_findings",
    }
    total = int(payload["summary"]["total_findings"])
    assert completed.returncode == (1 if total > 0 else 0)
