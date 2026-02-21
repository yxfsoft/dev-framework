#!/usr/bin/env python3
"""
fw_utils.py — 框架脚本共享工具函数

提供工具链检测、pytest 输出解析、配置加载等公共函数，
供 run-baseline.py、check-quality-gate.py、run-verify.py 等脚本复用。
"""

from __future__ import annotations  # M35/M36: 支持 Python 3.7+ 新式类型注解

import json
import re
import shlex
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


# ============================================================
# Phase 常量（全局唯一定义，所有脚本共用）
# ============================================================

PHASE_ORDER = ["phase_0", "phase_1", "phase_2", "phase_3", "phase_3.5", "phase_4", "phase_5"]
PHASE_NUMS = [0, 1, 2, 3, 3.5, 4, 5]


# ============================================================
# 工具链检测
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

    # 验证检测到的工具是否在 PATH 中
    for key in ("test_runner", "linter", "formatter", "python"):
        cmd = detected[key]
        # 提取命令的第一个词（如 "uv run pytest" → "uv"）
        first_word = cmd.split()[0] if cmd else ""
        if first_word and first_word != sys.executable and shutil.which(first_word) is None:
            print(f"  [WARN] {key}: 命令 '{first_word}' 不在 PATH 中，回退到标准 Python")
            # 回退到标准 Python 命令
            if key == "test_runner":
                detected[key] = f"{sys.executable} -m pytest"
            elif key == "linter":
                detected[key] = f"{sys.executable} -m ruff check ."
            elif key == "formatter":
                detected[key] = f"{sys.executable} -m ruff format --check ."
            elif key == "python":
                detected[key] = sys.executable

    return detected


def build_test_cmd(toolchain: dict, test_dir: str, extra_args: list[str] | None = None) -> list[str]:
    """根据工具链构建 pytest 命令行列表。"""
    base = shlex.split(toolchain.get("test_runner", f"{sys.executable} -m pytest"))
    cmd = base + [test_dir]
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def build_lint_cmd(toolchain: dict) -> list[str]:
    """根据工具链构建 lint 命令行列表。"""
    return shlex.split(toolchain.get("linter", f"{sys.executable} -m ruff check ."))


# ============================================================
# pytest 输出解析
# ============================================================


def parse_pytest_passed(output: str) -> int:
    """从 pytest 输出中解析 passed 数量（简化版）。"""
    match = re.search(r"(\d+) passed", output)
    return int(match.group(1)) if match else 0


def parse_pytest_output(output: str) -> dict:
    """从 pytest 输出中解析 passed/failed/skipped 数量，返回三元组字典。"""
    result = {"passed": 0, "failed": 0, "skipped": 0}
    for key in result:
        match = re.search(rf"(\d+) {key}", output)
        if match:
            result[key] = int(match.group(1))
    return result


# ============================================================
# 配置加载
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
    """加载 session-state.json，返回字典。缺失或损坏文件返回空字典。"""
    state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: 读取 session-state.json 失败: {e}")
        return {}


def load_baseline(project_dir: Path) -> dict | None:
    """加载 baseline.json，返回字典。缺失或损坏文件返回 None。"""
    baseline_path = project_dir / ".claude" / "dev-state" / "baseline.json"
    if not baseline_path.exists():
        return None
    try:
        return json.loads(baseline_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: 读取 baseline.json 失败: {e}")
        return None


def validate_manifest(manifest: dict) -> list[str]:
    """校验 manifest.json 数据完整性，返回错误列表（空列表=通过）。"""
    errors: list[str] = []
    required_fields = ["id", "mode", "status", "created_at", "phase"]
    for field in required_fields:
        if field not in manifest:
            errors.append(f"缺少必填字段: {field}")
    mid = manifest.get("id", "")
    if mid and not re.match(r"^iter-\d+$", mid):
        errors.append(f"id 格式无效: '{mid}'（期望 iter-N）")
    mode = manifest.get("mode", "")
    if mode and mode not in ("init", "iterate"):
        errors.append(f"mode 值无效: '{mode}'（期望 init 或 iterate）")
    phase = manifest.get("phase", "")
    if phase and not re.match(r"^phase_\d+(\.5)?$", phase):
        errors.append(f"phase 格式无效: '{phase}'（期望 phase_N 或 phase_N.5）")
    return errors


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


# ============================================================
# 框架目录定位
# ============================================================

def get_framework_dir() -> Path:
    """获取框架根目录。支持 DEV_FRAMEWORK_DIR 环境变量覆盖。"""
    import os
    env_dir = os.environ.get("DEV_FRAMEWORK_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parent.parent
