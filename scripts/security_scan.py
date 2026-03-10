from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


def scan_security(*, root: Path) -> dict[str, Any]:
    dependency_vulns = _scan_dependency_vulns(root)
    secret_leaks = _scan_secret_leaks(root)
    policy_violations = _scan_policy_violations(root)
    summary = {
        "dependency_vulns": len(dependency_vulns),
        "secret_leaks": len(secret_leaks),
        "policy_violations": len(policy_violations),
    }
    summary["total_findings"] = (
        summary["dependency_vulns"]
        + summary["secret_leaks"]
        + summary["policy_violations"]
    )
    return {
        "dependency_vulns": dependency_vulns,
        "secret_leaks": secret_leaks,
        "policy_violations": policy_violations,
        "summary": summary,
    }


def _scan_dependency_vulns(root: Path) -> list[dict[str, Any]]:
    cmd = ["uv", "run", "pip-audit", "-f", "json"]
    try:
        completed = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    except Exception as exc:  # noqa: BLE001
        return [{"tool": "pip-audit", "status": "error", "message": str(exc)}]

    if completed.returncode != 0 and not completed.stdout.strip():
        return [
            {
                "tool": "pip-audit",
                "status": "error",
                "message": completed.stderr.strip() or "pip-audit failed",
            }
        ]

    try:
        data = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return []

    findings: list[dict[str, Any]] = []
    if isinstance(data, list):
        for package in data:
            name = str(package.get("name", ""))
            version = str(package.get("version", ""))
            vulns = package.get("vulns", [])
            if not isinstance(vulns, list):
                continue
            for vuln in vulns:
                findings.append(
                    {
                        "package": name,
                        "installed_version": version,
                        "id": str(vuln.get("id", "unknown")),
                        "fix_versions": vuln.get("fix_versions", []),
                    }
                )
    return findings


def _scan_secret_leaks(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    include_dirs = [root / "src", root / "scripts", root / ".github"]
    for directory in include_dirs:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".db", ".pyc"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for idx, line in enumerate(content.splitlines(), start=1):
                for pattern in SECRET_PATTERNS:
                    if pattern.search(line):
                        findings.append(
                            {
                                "file": str(path.relative_to(root)),
                                "line": idx,
                                "pattern": pattern.pattern,
                            }
                        )
                        break
    return findings


def _scan_policy_violations(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    release_guard = root / ".github/workflows/release_guard.yml"
    if not release_guard.exists():
        findings.append(
            {
                "policy": "release_guard_required",
                "message": "release_guard workflow is missing",
            }
        )
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run security baseline scan")
    parser.add_argument("--root", type=str, default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = scan_security(root=Path(args.root).resolve())
    print(json.dumps(payload, ensure_ascii=False))
    return 1 if int(payload["summary"]["total_findings"]) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
