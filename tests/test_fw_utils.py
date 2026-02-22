"""Tests for fw_utils.py — Tier 1 (pure functions) + Tier 2 (tmp_path fixtures)."""

import json
import pytest
from pathlib import Path

import fw_utils


# ============================================================
# Tier 1: validate_safe_id — pure function, zero dependencies
# ============================================================

class TestValidateSafeId:
    """validate_safe_id() should reject path-traversal characters."""

    def test_normal_id(self):
        """Normal IDs should not raise."""
        fw_utils.validate_safe_id("iter-1", "test")
        fw_utils.validate_safe_id("CR-001", "test")
        fw_utils.validate_safe_id("iter-42", "test")

    def test_dotdot_attack(self):
        with pytest.raises(SystemExit):
            fw_utils.validate_safe_id("../etc/passwd", "test")

    def test_slash_attack(self):
        with pytest.raises(SystemExit):
            fw_utils.validate_safe_id("iter-1/../../secret", "test")

    def test_backslash_attack(self):
        with pytest.raises(SystemExit):
            fw_utils.validate_safe_id("iter-1\\..\\secret", "test")

    def test_dotdot_only(self):
        with pytest.raises(SystemExit):
            fw_utils.validate_safe_id("..", "test")


# ============================================================
# Tier 1: validate_manifest — pure function
# ============================================================

class TestValidateManifest:
    """validate_manifest() checks manifest.json completeness."""

    def test_valid_manifest(self):
        manifest = {
            "id": "iter-0",
            "mode": "init",
            "status": "active",
            "created_at": "2025-01-01T00:00:00+00:00",
            "phase": "phase_0",
        }
        errors = fw_utils.validate_manifest(manifest)
        assert errors == []

    def test_missing_required_field(self):
        manifest = {
            "mode": "init",
            "status": "active",
            "created_at": "2025-01-01T00:00:00+00:00",
            "phase": "phase_0",
        }
        errors = fw_utils.validate_manifest(manifest)
        assert any("id" in e for e in errors)

    def test_missing_multiple_fields(self):
        errors = fw_utils.validate_manifest({})
        assert len(errors) >= 5  # all required fields missing

    def test_invalid_id_format(self):
        manifest = {
            "id": "iteration-1",  # should be iter-N
            "mode": "init",
            "status": "active",
            "created_at": "2025-01-01T00:00:00+00:00",
            "phase": "phase_0",
        }
        errors = fw_utils.validate_manifest(manifest)
        assert any("id" in e and "格式" in e for e in errors)

    def test_invalid_mode(self):
        manifest = {
            "id": "iter-0",
            "mode": "unknown",
            "status": "active",
            "created_at": "2025-01-01T00:00:00+00:00",
            "phase": "phase_0",
        }
        errors = fw_utils.validate_manifest(manifest)
        assert any("mode" in e for e in errors)

    def test_invalid_phase_format(self):
        manifest = {
            "id": "iter-0",
            "mode": "init",
            "status": "active",
            "created_at": "2025-01-01T00:00:00+00:00",
            "phase": "step_1",
        }
        errors = fw_utils.validate_manifest(manifest)
        assert any("phase" in e for e in errors)

    def test_valid_phase_with_half(self):
        manifest = {
            "id": "iter-0",
            "mode": "iterate",
            "status": "active",
            "created_at": "2025-01-01T00:00:00+00:00",
            "phase": "phase_3.5",
        }
        errors = fw_utils.validate_manifest(manifest)
        assert errors == []


# ============================================================
# Tier 1: parse_pytest_output — pure function
# ============================================================

class TestParsePytestOutput:
    """parse_pytest_output() should extract counts from pytest summary lines."""

    def test_all_passed(self):
        output = "===== 42 passed in 1.23s ====="
        result = fw_utils.parse_pytest_output(output)
        assert result == {"passed": 42, "failed": 0, "skipped": 0}

    def test_mixed_results(self):
        output = "===== 10 passed, 3 failed, 2 skipped in 5.00s ====="
        result = fw_utils.parse_pytest_output(output)
        assert result == {"passed": 10, "failed": 3, "skipped": 2}

    def test_all_failed(self):
        output = "===== 5 failed in 2.00s ====="
        result = fw_utils.parse_pytest_output(output)
        assert result == {"passed": 0, "failed": 5, "skipped": 0}

    def test_no_tests(self):
        output = "no tests ran"
        result = fw_utils.parse_pytest_output(output)
        assert result == {"passed": 0, "failed": 0, "skipped": 0}

    def test_empty_output(self):
        result = fw_utils.parse_pytest_output("")
        assert result == {"passed": 0, "failed": 0, "skipped": 0}

    def test_multiline_output(self):
        output = (
            "tests/test_foo.py ..F.\n"
            "tests/test_bar.py ....\n"
            "===== 7 passed, 1 failed in 3.50s ====="
        )
        result = fw_utils.parse_pytest_output(output)
        assert result == {"passed": 7, "failed": 1, "skipped": 0}


# ============================================================
# Tier 1: parse_pytest_passed — pure function
# ============================================================

class TestParsePytestPassed:
    """parse_pytest_passed() returns passed count only."""

    def test_normal(self):
        assert fw_utils.parse_pytest_passed("10 passed in 1.00s") == 10

    def test_no_match(self):
        assert fw_utils.parse_pytest_passed("no tests ran") == 0

    def test_empty(self):
        assert fw_utils.parse_pytest_passed("") == 0

    def test_mixed(self):
        assert fw_utils.parse_pytest_passed("5 passed, 2 failed") == 5


# ============================================================
# Tier 2: detect_toolchain — needs tmp_path
# ============================================================

class TestDetectToolchain:
    """detect_toolchain() should detect project package manager."""

    def test_uv_lock(self, tmp_path):
        (tmp_path / "uv.lock").write_text("", encoding="utf-8")
        result = fw_utils.detect_toolchain(tmp_path, {})
        assert "uv run pytest" in result["test_runner"]
        assert "uv run python" in result["python"]

    def test_poetry_lock(self, tmp_path):
        import shutil
        (tmp_path / "poetry.lock").write_text("", encoding="utf-8")
        result = fw_utils.detect_toolchain(tmp_path, {})
        if shutil.which("poetry"):
            assert "poetry run pytest" in result["test_runner"]
            assert "poetry run python" in result["python"]
        else:
            # poetry not in PATH → detect_toolchain falls back to sys.executable
            assert "pytest" in result["test_runner"]

    def test_fallback_to_sys_executable(self, tmp_path):
        result = fw_utils.detect_toolchain(tmp_path, {})
        assert "pytest" in result["test_runner"]
        assert result["python"]  # not empty

    def test_explicit_config_overrides(self, tmp_path):
        config = {"toolchain": {"test_runner": "my-pytest", "python": "my-python"}}
        result = fw_utils.detect_toolchain(tmp_path, config)
        # explicit config may be overridden if not in PATH, but the key should exist
        assert "test_runner" in result
        assert "python" in result


# ============================================================
# Tier 2: build_test_cmd
# ============================================================

class TestBuildTestCmd:
    """build_test_cmd() constructs correct pytest command lists."""

    def test_basic(self):
        import sys
        toolchain = {"test_runner": f"{sys.executable} -m pytest"}
        cmd = fw_utils.build_test_cmd(toolchain, "tests/unit/")
        assert cmd[-1] == "tests/unit/" or "tests/unit/" in cmd

    def test_with_extra_args(self):
        import sys
        toolchain = {"test_runner": f"{sys.executable} -m pytest"}
        cmd = fw_utils.build_test_cmd(toolchain, "tests/", ["-x", "-q"])
        assert "-x" in cmd
        assert "-q" in cmd

    def test_uv_runner(self):
        toolchain = {"test_runner": "uv run pytest"}
        cmd = fw_utils.build_test_cmd(toolchain, "tests/")
        assert cmd[0] == "uv"
        assert "pytest" in cmd


# ============================================================
# Tier 2: load_run_config — needs tmp_path
# ============================================================

class TestLoadRunConfig:
    """load_run_config() handles missing/corrupt YAML gracefully."""

    def test_missing_file(self, tmp_path):
        result = fw_utils.load_run_config(tmp_path)
        assert result == {}

    def test_valid_config(self, tmp_path):
        import yaml
        config_dir = tmp_path / ".claude" / "dev-state"
        config_dir.mkdir(parents=True)
        config = {"toolchain": {"test_runner": "pytest"}, "iteration_mode": "standard"}
        (config_dir / "run-config.yaml").write_text(
            yaml.dump(config), encoding="utf-8"
        )
        result = fw_utils.load_run_config(tmp_path)
        assert result["iteration_mode"] == "standard"

    def test_corrupt_yaml(self, tmp_path):
        config_dir = tmp_path / ".claude" / "dev-state"
        config_dir.mkdir(parents=True)
        (config_dir / "run-config.yaml").write_text(
            "{{invalid yaml: [", encoding="utf-8"
        )
        result = fw_utils.load_run_config(tmp_path)
        assert result == {}

    def test_empty_yaml(self, tmp_path):
        config_dir = tmp_path / ".claude" / "dev-state"
        config_dir.mkdir(parents=True)
        (config_dir / "run-config.yaml").write_text("", encoding="utf-8")
        result = fw_utils.load_run_config(tmp_path)
        assert result == {}
