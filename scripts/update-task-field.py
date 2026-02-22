#!/usr/bin/env python3
"""update-task-field.py — Restricted YAML field writer for Verifier/Reviewer sub-agents.

Part of the v4.0 sub-agent architecture. This script provides a safe,
whitelist-controlled interface for Verifier and Reviewer sub-agents to
update specific fields in task YAML files without risking corruption of
protected fields (id, type, design, etc.).

Usage:
    python scripts/update-task-field.py \\
        --project-dir "." \\
        --iteration-id "iter-1" \\
        --task-id "CR-001" \\
        --field "done_evidence" \\
        --value '{"tests":[...],"logs":[...],"notes":[...]}'

    python scripts/update-task-field.py \\
        --project-dir "." \\
        --iteration-id "iter-1" \\
        --task-id "CR-001" \\
        --field "status" \\
        --value "PASS"

    python scripts/update-task-field.py \\
        --project-dir "." \\
        --iteration-id "iter-1" \\
        --task-id "CR-001" \\
        --field "notes" \\
        --value "Reviewer noticed edge case in error handling"

Exit codes:
    0 — Success
    1 — Validation error (bad field, bad value, schema mismatch)
    2 — File not found
"""

import argparse
import json
import os
import sys

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Field policies
# ---------------------------------------------------------------------------

ALLOWED_STATUS_VALUES = frozenset({"ready_for_review", "rework", "PASS"})

ALLOWED_CURRENT_STEP_VALUES = frozenset({
    "reading_code", "coding", "self_check", "testing",
    "regression", "committing", "ready_for_verify",
})

WRITABLE_FIELDS = frozenset({
    "status", "done_evidence", "review_result", "notes", "current_step",
})

BLACKLISTED_FIELDS = frozenset({
    "id", "type", "design", "affected_files", "acceptance_criteria", "depends",
})

DONE_EVIDENCE_REQUIRED_KEYS = {"tests", "logs", "notes"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_task_path(project_dir: str, iteration_id: str, task_id: str) -> str:
    return os.path.join(
        project_dir, ".claude", "dev-state", iteration_id, "tasks", f"{task_id}.yaml"
    )


def _parse_json_value(raw: str, field_name: str) -> dict:
    """Parse a JSON string and return a dict, or exit with code 1."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: --value for '{field_name}' is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(obj, dict):
        print(f"Error: --value for '{field_name}' must be a JSON object, got {type(obj).__name__}", file=sys.stderr)
        sys.exit(1)
    return obj


def _validate_done_evidence(obj: dict) -> None:
    missing = DONE_EVIDENCE_REQUIRED_KEYS - obj.keys()
    if missing:
        print(
            f"Error: done_evidence is missing required keys: {', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def update_field(task_data: dict, field: str, raw_value: str) -> dict:
    """Validate and apply a single field update. Returns the modified task_data."""

    # --- Blacklist check ---
    if field in BLACKLISTED_FIELDS:
        print(f"Error: field '{field}' is protected and cannot be written by sub-agents", file=sys.stderr)
        sys.exit(1)

    # --- Whitelist check ---
    if field not in WRITABLE_FIELDS:
        print(
            f"Error: field '{field}' is not in the writable whitelist. "
            f"Allowed fields: {', '.join(sorted(WRITABLE_FIELDS))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Per-field validation & application ---

    if field == "status":
        if raw_value not in ALLOWED_STATUS_VALUES:
            print(
                f"Error: invalid status '{raw_value}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_STATUS_VALUES))}",
                file=sys.stderr,
            )
            sys.exit(1)
        task_data[field] = raw_value

    elif field == "current_step":
        if raw_value not in ALLOWED_CURRENT_STEP_VALUES:
            print(
                f"Error: invalid current_step '{raw_value}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_CURRENT_STEP_VALUES))}",
                file=sys.stderr,
            )
            sys.exit(1)
        task_data[field] = raw_value

    elif field == "done_evidence":
        obj = _parse_json_value(raw_value, field)
        _validate_done_evidence(obj)
        task_data[field] = obj

    elif field == "review_result":
        obj = _parse_json_value(raw_value, field)
        task_data[field] = obj

    elif field == "notes":
        existing = task_data.get("notes")
        if existing is None:
            task_data["notes"] = raw_value
        elif isinstance(existing, list):
            existing.append(raw_value)
        elif isinstance(existing, str):
            task_data["notes"] = existing + "\n" + raw_value
        else:
            # Unexpected type — convert to list and append
            task_data["notes"] = [existing, raw_value]

    return task_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restricted YAML field writer for Verifier/Reviewer sub-agents (v4.0).",
    )
    parser.add_argument("--project-dir", required=True, help="Root directory of the project")
    parser.add_argument("--iteration-id", required=True, help="Iteration identifier (e.g. iter-1)")
    parser.add_argument("--task-id", required=True, help="Task identifier (e.g. CR-001)")
    parser.add_argument("--field", required=True, help="Field name to update")
    parser.add_argument("--value", required=True, help="New value (plain string or JSON)")
    args = parser.parse_args()

    # 路径遍历校验
    for _label, _val in [("iteration-id", args.iteration_id), ("task-id", args.task_id)]:
        if ".." in _val or "/" in _val or "\\" in _val:
            print(f"Error: {_label} contains illegal characters: {_val}", file=sys.stderr)
            sys.exit(1)

    task_path = _resolve_task_path(args.project_dir, args.iteration_id, args.task_id)

    if not os.path.isfile(task_path):
        print(f"Error: task file not found: {task_path}", file=sys.stderr)
        sys.exit(2)

    with open(task_path, "r", encoding="utf-8") as fh:
        task_data = yaml.safe_load(fh) or {}

    task_data = update_field(task_data, args.field, args.value)

    with open(task_path, "w", encoding="utf-8") as fh:
        yaml.dump(task_data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"OK: {args.field} updated in {task_path}")


if __name__ == "__main__":
    main()
