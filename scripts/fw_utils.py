#!/usr/bin/env python3
"""
fw_utils.py — 框架脚本共享工具函数

提供工具链检测、pytest 输出解析、配置加载等公共函数，
供 run-baseline.py、check-quality-gate.py、run-verify.py 等脚本复用。

v2.6 新增（FIX-01 + FIX-13）
"""

from __future__ import annotations  # M35/M36: 支持 Python 3.7+ 新式类型注解

import json
import re
import shlex
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


# ============================================================
# 工具链检测（FIX-01）
# ============================================================

def detect_toolchain(project_dir: Path, config: dict) -> dict:
    """自动检测项目工具链，返回实际可用的命令。

    检测优先级：
    1. run-config.yaml 中的显式配置（非 "auto"）
    2. 项目根目录下的 uv.lock → uv run
    3. 项目根目录下的 poetry.lock → poetry run
    4. 回退到标准 Python
    """
    toolchain = config.get("toolchain", {})
    detected = {}

    # --- test_runner ---
    if toolchain.get("test_runner", "auto") != "auto":
        detected["test_runner"] = toolchain["test_runner"]
    elif (project_dir / "uv.lock").exists():
        detected["test_runner"] = "uv run pytest"
    elif (project_dir / "poetry.lock").exists():
        detected["test_runner"] = "poetry run pytest"
    else:
        detected["test_runner"] = f"{sys.executable} -m pytest"

    # --- linter ---
    if toolchain.get("linter", "auto") != "auto":
        detected["linter"] = toolchain["linter"]
    elif (project_dir / "uv.lock").exists():
        detected["linter"] = "uv run ruff check ."
    elif (project_dir / "poetry.lock").exists():
        detected["linter"] = "poetry run ruff check ."
    else:
        detected["linter"] = f"{sys.executable} -m ruff check ."

    # --- formatter ---
    if toolchain.get("formatter", "auto") != "auto":
        detected["formatter"] = toolchain["formatter"]
    elif (project_dir / "uv.lock").exists():
        detected["formatter"] = "uv run ruff format --check ."
    elif (project_dir / "poetry.lock").exists():
        detected["formatter"] = "poetry run ruff format --check ."
    else:
        detected["formatter"] = f"{sys.executable} -m ruff format --check ."

    # --- python ---
    if toolchain.get("python", "auto") != "auto":
        detected["python"] = toolchain["python"]
    elif (project_dir / "uv.lock").exists():
        detected["python"] = "uv run python"
    elif (project_dir / "poetry.lock").exists():
        detected["python"] = "poetry run python"
    else:
        detected["python"] = sys.executable

    return detected


def build_test_cmd(toolchain: dict, test_dir: str, extra_args: list[str] | None = None) -> list[str]:
    """根据工具链构建 pytest 命令行列表。"""
    base = shlex.split(toolchain["test_runner"])
    cmd = base + [test_dir]
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def build_lint_cmd(toolchain: dict) -> list[str]:
    """根据工具链构建 lint 命令行列表。"""
    return shlex.split(toolchain["linter"])


# ============================================================
# pytest 输出解析（FIX-13: 从 run-baseline.py 提取复用）
# ============================================================

def parse_pytest_output(output: str) -> dict:
    """解析 pytest 输出，提取 passed/failed/skipped 数量。

    依赖 pytest 标准汇总行格式，如 "5 passed, 1 failed, 2 skipped"。
    """
    result = {"passed": 0, "failed": 0, "skipped": 0}
    patterns = {
        "passed": r"(\d+) passed",
        "failed": r"(\d+) failed",
        "skipped": r"(\d+) skipped",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            result[key] = int(match.group(1))
    return result


def parse_pytest_passed(output: str) -> int:
    """从 pytest 输出中解析 passed 数量（简化版）。"""
    match = re.search(r"(\d+) passed", output)
    return int(match.group(1)) if match else 0


# ============================================================
# 配置加载（FIX-13: 统一配置加载逻辑）
# ============================================================

def load_run_config(project_dir: Path) -> dict:
    """加载 run-config.yaml 配置，返回字典。缺失文件返回空字典。"""
    config_path = project_dir / ".claude" / "dev-state" / "run-config.yaml"
    if not config_path.exists():
        return {}
    if yaml is None:
        print("WARNING: PyYAML 未安装，无法加载 run-config.yaml，返回空配置")
        return {}
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def load_session_state(project_dir: Path) -> dict:
    """加载 session-state.json，返回字典。缺失文件返回空字典。"""
    state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


def load_baseline(project_dir: Path) -> dict | None:
    """加载 baseline.json，返回字典。缺失文件返回 None。"""
    baseline_path = project_dir / ".claude" / "dev-state" / "baseline.json"
    if not baseline_path.exists():
        return None
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def load_task_yaml(task_path: Path) -> dict | None:
    """加载单个任务 YAML 文件，返回字典。"""
    if yaml is None:
        print("ERROR: PyYAML 未安装。运行: pip install PyYAML>=6.0")
        return None
    if not task_path.exists():
        return None
    return yaml.safe_load(task_path.read_text(encoding="utf-8"))


def save_task_yaml(task_path: Path, task: dict) -> None:
    """保存任务 YAML 文件。

    注意：yaml.dump 会丢失原文件注释。
    """
    if yaml is None:
        print("ERROR: PyYAML 未安装，无法保存任务文件")
        return
    task_path.write_text(
        yaml.dump(task, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
