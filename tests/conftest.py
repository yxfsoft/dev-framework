"""Shared fixtures for dev-framework tests."""

import json
import pytest
from pathlib import Path


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project directory structure for testing."""
    dev_state = tmp_path / ".claude" / "dev-state"
    dev_state.mkdir(parents=True)

    # session-state.json
    session_state = {
        "session_id": "ses-test",
        "current_iteration": "iter-0",
        "current_phase": "phase_0",
        "progress": {
            "total_tasks": 0,
            "completed": 0,
            "in_progress": 0,
            "pending": 0,
            "ready_for_verify": 0,
            "ready_for_review": 0,
            "rework": 0,
            "failed": 0,
            "blocked": 0,
            "timeout": 0,
        },
    }
    (dev_state / "session-state.json").write_text(
        json.dumps(session_state, indent=2), encoding="utf-8"
    )

    # baseline.json
    baseline = {
        "iteration": "iter-0",
        "timestamp": "2025-01-01T00:00:00+00:00",
        "git_commit": "",
        "test_results": {
            "l1_passed": 0,
            "l1_failed": 0,
            "l1_skipped": 0,
            "l2_passed": 0,
            "l2_failed": 0,
            "l2_skipped": 0,
        },
        "lint_clean": True,
        "pre_existing_failures": [],
    }
    (dev_state / "baseline.json").write_text(
        json.dumps(baseline, indent=2), encoding="utf-8"
    )

    return tmp_path


@pytest.fixture
def tmp_project_with_iter(tmp_project):
    """Create a project with an iteration directory containing tasks."""
    iter_dir = tmp_project / ".claude" / "dev-state" / "iter-1"
    tasks_dir = iter_dir / "tasks"
    verify_dir = iter_dir / "verify"
    tasks_dir.mkdir(parents=True)
    verify_dir.mkdir(parents=True)
    (iter_dir / "checkpoints").mkdir(parents=True)

    manifest = {
        "id": "iter-1",
        "mode": "iterate",
        "status": "active",
        "created_at": "2025-01-01T00:00:00+00:00",
        "phase": "phase_3",
    }
    (iter_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    return tmp_project
