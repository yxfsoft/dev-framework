"""Tests for update-task-field.py — whitelist/blacklist/value validation."""

import json
import pytest
import sys
from pathlib import Path

# update-task-field.py has a hyphen in filename, import via importlib
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "update_task_field",
    Path(__file__).resolve().parent.parent / "scripts" / "update-task-field.py",
)
assert _spec is not None and _spec.loader is not None
update_task_field = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(update_task_field)

update_field = update_task_field.update_field
WRITABLE_FIELDS = update_task_field.WRITABLE_FIELDS
BLACKLISTED_FIELDS = update_task_field.BLACKLISTED_FIELDS
ALLOWED_STATUS_VALUES = update_task_field.ALLOWED_STATUS_VALUES


# ============================================================
# Whitelist / Blacklist checks
# ============================================================

class TestFieldAccess:
    """Fields must obey whitelist/blacklist rules."""

    def test_blacklisted_field_rejected(self):
        for field in BLACKLISTED_FIELDS:
            with pytest.raises(SystemExit):
                update_field({}, field, "anything")

    def test_unknown_field_rejected(self):
        with pytest.raises(SystemExit):
            update_field({}, "nonexistent_field", "value")

    def test_writable_fields_accepted(self):
        """All writable fields should be processable (may fail on value validation)."""
        for field in WRITABLE_FIELDS:
            # We just verify the field name itself passes the whitelist check.
            # Value validation may still reject, so we provide valid values per field.
            task = {}
            if field == "status":
                task = update_field(task, field, "PASS")
            elif field == "current_step":
                task = update_field(task, field, "coding")
            elif field == "done_evidence":
                task = update_field(task, field, json.dumps({"tests": [], "logs": [], "notes": []}))
            elif field == "review_result":
                task = update_field(task, field, json.dumps({"verdict": "PASS"}))
            elif field == "notes":
                task = update_field(task, field, "a note")
            assert field in task


# ============================================================
# Status field validation
# ============================================================

class TestStatusField:
    """Status field must be in the allowed set."""

    def test_valid_statuses(self):
        for status in ALLOWED_STATUS_VALUES:
            task = update_field({}, "status", status)
            assert task["status"] == status

    def test_invalid_status_rejected(self):
        with pytest.raises(SystemExit):
            update_field({}, "status", "pending")

    def test_invalid_status_in_progress(self):
        with pytest.raises(SystemExit):
            update_field({}, "status", "in_progress")


# ============================================================
# current_step field validation
# ============================================================

class TestCurrentStepField:
    """current_step must be in the allowed set."""

    def test_valid_step(self):
        task = update_field({}, "current_step", "coding")
        assert task["current_step"] == "coding"

    def test_invalid_step_rejected(self):
        with pytest.raises(SystemExit):
            update_field({}, "current_step", "hacking")


# ============================================================
# done_evidence validation
# ============================================================

class TestDoneEvidence:
    """done_evidence must be valid JSON with required keys."""

    def test_valid_evidence(self):
        evidence = {"tests": ["t1"], "logs": ["l1"], "notes": ["n1"]}
        task = update_field({}, "done_evidence", json.dumps(evidence))
        assert task["done_evidence"] == evidence

    def test_missing_required_key(self):
        evidence = {"tests": ["t1"], "logs": ["l1"]}  # missing "notes"
        with pytest.raises(SystemExit):
            update_field({}, "done_evidence", json.dumps(evidence))

    def test_invalid_json(self):
        with pytest.raises(SystemExit):
            update_field({}, "done_evidence", "not json")

    def test_non_dict_json(self):
        with pytest.raises(SystemExit):
            update_field({}, "done_evidence", json.dumps(["a", "b"]))


# ============================================================
# review_result
# ============================================================

class TestReviewResult:
    """review_result accepts any valid JSON object."""

    def test_valid_review(self):
        review = {"verdict": "PASS", "issues": []}
        task = update_field({}, "review_result", json.dumps(review))
        assert task["review_result"] == review

    def test_invalid_json(self):
        with pytest.raises(SystemExit):
            update_field({}, "review_result", "{bad json")


# ============================================================
# notes (append behavior)
# ============================================================

class TestNotes:
    """notes field should append, not overwrite."""

    def test_new_note_on_empty(self):
        task = update_field({}, "notes", "first note")
        assert task["notes"] == "first note"

    def test_append_to_string(self):
        task = {"notes": "first"}
        task = update_field(task, "notes", "second")
        assert "first" in task["notes"]
        assert "second" in task["notes"]

    def test_append_to_list(self):
        task = {"notes": ["first"]}
        task = update_field(task, "notes", "second")
        assert "second" in task["notes"]
        assert len(task["notes"]) == 2
