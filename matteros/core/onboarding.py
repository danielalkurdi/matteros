from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from matteros.core.audit import AuditLogger, VerificationResult
from matteros.core.playbook import PlaybookError, load_playbook
from matteros.core.runner import RunnerOptions, WorkflowRunner
from matteros.core.types import RunSummary


@dataclass(slots=True)
class OnboardingStatus:
    config_present: bool
    auth_ready: bool
    llm_ready: bool
    playbook_ready: bool
    smoke_test_passed: bool
    details: dict[str, Any]


def ensure_home_scaffold(*, home: Path) -> dict[str, Path]:
    home.mkdir(parents=True, exist_ok=True)
    audit_dir = home / "audit"
    auth_dir = home / "auth"
    playbooks_dir = home / "playbooks"
    fixtures_dir = home / "fixtures" / "ms_graph"
    exports_dir = home / "exports"
    plugins_dir = home / "plugins"

    audit_dir.mkdir(parents=True, exist_ok=True)
    auth_dir.mkdir(parents=True, exist_ok=True)
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    sample_playbook_path = playbooks_dir / "daily_time_capture.yml"
    if not sample_playbook_path.exists():
        sample = (Path(__file__).resolve().parents[1] / "playbooks" / "daily_time_capture.yml").read_text(
            encoding="utf-8"
        )
        sample_playbook_path.write_text(sample, encoding="utf-8")

    _ensure_fixture_files(fixtures_dir)

    return {
        "home": home,
        "audit_dir": audit_dir,
        "auth_dir": auth_dir,
        "playbooks_dir": playbooks_dir,
        "fixtures_dir": fixtures_dir,
        "exports_dir": exports_dir,
        "plugins_dir": plugins_dir,
        "sample_playbook": sample_playbook_path,
    }


def smoke_test_dry_run(
    *,
    runner: WorkflowRunner,
    audit: AuditLogger,
    playbook_path: Path,
    workspace_path: Path,
    fixtures_root: Path,
    output_csv_path: Path,
    reviewer: str,
) -> tuple[RunSummary | None, VerificationResult | None, str | None]:
    try:
        playbook = load_playbook(playbook_path)
    except PlaybookError as exc:
        return None, None, str(exc)

    try:
        summary = runner.run(
            playbook=playbook,
            inputs={
                "date": "2026-02-20",
                "workspace_path": str(workspace_path),
                "fixtures_root": str(fixtures_root),
                "output_csv_path": str(output_csv_path),
                "matter_hint": "",
            },
            options=RunnerOptions(
                dry_run=True,
                approve_mode=False,
                reviewer=reviewer,
            ),
        )
    except Exception as exc:
        return None, None, str(exc)

    verify = audit.verify_run(run_id=summary.run_id, source="both")
    if not verify.ok:
        return summary, verify, f"audit verification failed: {verify.reason}"

    return summary, verify, None


def build_onboarding_status(
    *,
    config_present: bool,
    auth_ready: bool,
    llm_ready: bool,
    playbook_path: Path,
    smoke_status: str | None,
    smoke_run_id: str | None,
) -> OnboardingStatus:
    playbook_ready = playbook_path.exists()
    smoke_test_passed = smoke_status == "passed"

    details = {
        "playbook_path": str(playbook_path),
        "smoke_status": smoke_status,
        "smoke_run_id": smoke_run_id,
    }

    return OnboardingStatus(
        config_present=config_present,
        auth_ready=auth_ready,
        llm_ready=llm_ready,
        playbook_ready=playbook_ready,
        smoke_test_passed=smoke_test_passed,
        details=details,
    )


def _ensure_fixture_files(fixtures_dir: Path) -> None:
    calendar_path = fixtures_dir / "calendar_events.json"
    if not calendar_path.exists():
        calendar_path.write_text(
            json.dumps(
                [
                    {
                        "id": "onboard-cal-1",
                        "subject": "MAT-123 Onboarding call",
                        "start": {"dateTime": "2026-02-20T09:00:00Z"},
                        "end": {"dateTime": "2026-02-20T09:45:00Z"},
                    }
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

    sent_path = fixtures_dir / "sent_emails.json"
    if not sent_path.exists():
        sent_path.write_text(
            json.dumps(
                [
                    {
                        "id": "onboard-mail-1",
                        "subject": "Re: MAT-123 onboarding summary",
                        "sentDateTime": "2026-02-20T10:15:00Z",
                    }
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
