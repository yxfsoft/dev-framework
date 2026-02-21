#!/usr/bin/env python3
"""
auto-loop-runner.py — AutoLoop 外围循环脚本

在 auto-loop 模式下，当 Claude 会话因上下文耗尽或其他原因结束时，
此脚本自动重启新会话继续执行，直到所有任务完成或触发安全阀。

注意：此脚本设计为单实例运行。不支持同一项目同时启动多个 AutoLoop 实例，
session-state.json 的写入使用原子替换但无文件锁，并发写入可能导致数据丢失。

用法:
    python dev-framework/scripts/auto-loop-runner.py \
        --project-dir "/path/to/project" \
        --iteration-id "iter-1"

    # 自定义最大重启次数
    python dev-framework/scripts/auto-loop-runner.py \
        --project-dir "/path/to/project" \
        --iteration-id "iter-1" \
        --max-restarts 5
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── 框架内部导入 ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import load_run_config, load_session_state, load_baseline


def _check_all_tasks_pass(dev_state: Path, iteration_id: str) -> bool:
    """检查是否所有任务都已 PASS。"""
    tasks_dir = dev_state / iteration_id / "tasks"
    if not tasks_dir.exists():
        return False

    task_files = list(tasks_dir.glob("*.yaml"))
    if not task_files:
        return False

    try:
        import yaml
    except ImportError:
        print("[ERROR] PyYAML 未安装")
        return False

    for tf in task_files:
        task = yaml.safe_load(tf.read_text(encoding="utf-8")) or {}
        status = task.get("status", "")
        if status != "PASS":
            return False

    return True


def _get_progress(project_dir: Path) -> int:
    """从 session-state.json 获取已完成任务数。"""
    state = load_session_state(project_dir)
    if not state:
        return 0
    return state.get("progress", {}).get("completed", 0)


def _get_consecutive_failures(project_dir: Path) -> int:
    """从 session-state.json 获取连续失败次数。"""
    state = load_session_state(project_dir)
    if not state:
        return 0
    return state.get("consecutive_failures", 0)


def _build_prompt(project_dir: Path, iteration_id: str) -> str:
    """构建传递给 claude -p 的提示词。"""
    return (
        f"请按照 .claude/CLAUDE.md 中的框架运行时手册，以 auto-loop 模式继续开发。\n"
        f"当前迭代是 {iteration_id}。\n"
        f"请先执行强制启动协议（读取 run-config.yaml、session-state.json、context-snapshot.md），\n"
        f"然后继续未完成的任务。"
    )


def preflight_check(
    project_dir: Path, iteration_id: str, dev_state: Path
) -> list[str]:
    """启动前检查，返回错误列表（空列表表示通过）。"""
    errors = []

    # 检查 claude CLI 可用
    config = load_run_config(project_dir)
    auto_loop_cfg = config.get("auto_loop", {}) if config else {}
    claude_cmd = auto_loop_cfg.get("claude_command", "claude")
    if shutil.which(claude_cmd) is None:
        errors.append(f"claude CLI 不在 PATH 中（命令: {claude_cmd}），请先安装 Claude Code 或在 run-config.yaml 的 auto_loop.claude_command 中配置正确路径")

    # 检查项目目录
    if not dev_state.exists():
        errors.append(f".claude/dev-state/ 不存在: {dev_state}")

    # 检查迭代目录
    iter_dir = dev_state / iteration_id
    if not iter_dir.exists():
        errors.append(f"迭代目录不存在: {iter_dir}")

    # 检查 run-config.yaml mode（复用上面已加载的 config）
    if config:
        mode = config.get("mode", "")
        if mode != "auto-loop":
            errors.append(
                f"run-config.yaml 的 mode 不是 auto-loop（当前: {mode}）。"
                f"请修改 .claude/dev-state/run-config.yaml 中 mode: \"auto-loop\""
            )
    else:
        errors.append("无法读取 run-config.yaml")

    return errors


def _update_session_after_run(project_dir: Path, claude_failed: bool, progress_delta: int) -> None:
    """更新 session-state.json: consecutive_failures 和 last_test_results。"""
    state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
    if not state_path.exists():
        return
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] 读取 session-state.json 失败: {e}")
        return

    # C4: 更新 consecutive_failures
    if claude_failed or progress_delta == 0:
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        print(f"  consecutive_failures → {state['consecutive_failures']}")
    else:
        state["consecutive_failures"] = 0

    # H5: 写入 last_test_results
    baseline = load_baseline(project_dir)
    if baseline and "test_results" in baseline:
        state["last_test_results"] = {
            "l1_passed": baseline["test_results"].get("l1_passed", 0),
            "l1_failed": baseline["test_results"].get("l1_failed", 0),
        }

    # M14: 原子写入（write-to-temp-then-rename）
    tmp_path = state_path.parent / f".session-state-{os.getpid()}.tmp"
    try:
        tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(state_path)
    except OSError:
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def run_auto_loop(
    project_dir: Path, iteration_id: str, max_restarts: int
) -> bool:
    """运行 AutoLoop 外围循环，返回是否成功完成。"""
    dev_state = project_dir / ".claude" / "dev-state"

    print()
    print("=" * 60)
    print("  AutoLoop Runner v3.0")
    print("=" * 60)
    print(f"  项目目录: {project_dir}")
    print(f"  迭代: {iteration_id}")
    print(f"  最大重启次数: {max_restarts}")
    print()

    # Preflight
    errors = preflight_check(project_dir, iteration_id, dev_state)
    if errors:
        print("[PREFLIGHT FAILED]")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("[PREFLIGHT] 检查通过")
    print()

    # 复用 preflight_check 中已加载的 config，避免重复调用 load_run_config
    config = load_run_config(project_dir)  # TODO: 未来可改为从 preflight_check 传参
    auto_loop_cfg = config.get("auto_loop", {}) if config else {}
    max_consecutive_failures = auto_loop_cfg.get("max_consecutive_failures", 3)
    claude_timeout = auto_loop_cfg.get("claude_timeout", 7200)
    min_disk_mb = auto_loop_cfg.get("min_disk_mb", 100)
    no_progress_threshold = auto_loop_cfg.get("no_progress_threshold", 3)
    claude_command = auto_loop_cfg.get("claude_command", "claude")

    no_progress_count = 0

    for restart in range(max_restarts):
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{now}] === 第 {restart + 1}/{max_restarts} 次启动 ===")

        # 安全阀: git 冲突检查
        try:
            git_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(project_dir),
                capture_output=True, text=True, timeout=30,
            )
            if git_result.returncode == 0:
                for line in git_result.stdout.strip().splitlines():
                    if line and (line[0] == "U" or (len(line) > 1 and line[1] == "U")):
                        print("[SAFETY] git 工作区存在冲突文件，停止")
                        return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # git 不可用时跳过

        # 安全阀: 磁盘空间检查
        disk = shutil.disk_usage(str(project_dir))
        if disk.free < min_disk_mb * 1024 * 1024:
            print(f"[SAFETY] 磁盘剩余空间不足 ({disk.free // 1024 // 1024}MB < {min_disk_mb}MB)，停止")
            return False

        # 安全阀: 基线退化检查（非首次启动时）
        if restart > 0:
            baseline = load_baseline(project_dir)
            if baseline:
                baseline_passed = baseline.get("test_results", {}).get("l1_passed", 0)
                state = load_session_state(project_dir)
                current_passed = state.get("last_test_results", {}).get("l1_passed", baseline_passed) if state else baseline_passed
                if current_passed < baseline_passed:
                    print(f"[SAFETY] 基线退化: L1 passed {current_passed} < 基线 {baseline_passed}，停止")
                    return False

        # 1. 检查是否所有任务已完成
        if _check_all_tasks_pass(dev_state, iteration_id):
            print("[SUCCESS] 所有任务已 PASS，退出")
            return True

        # 2. 记录当前进度
        progress_before = _get_progress(project_dir)
        print(f"  当前已完成: {progress_before} 个任务")

        # 3. 检查安全阀
        consecutive_failures = _get_consecutive_failures(project_dir)
        if consecutive_failures >= max_consecutive_failures:
            print(f"[SAFETY] 连续失败 {consecutive_failures} 次（阈值 {max_consecutive_failures}），停止")
            return False

        # 4. 构建提示词并启动 claude
        prompt = _build_prompt(project_dir, iteration_id)
        print(f"  启动 claude -p ...")

        claude_failed = False
        try:
            result = subprocess.run(
                [claude_command, "-p", prompt],
                cwd=str(project_dir),
                timeout=claude_timeout,
            )
            print(f"  claude 退出码: {result.returncode}")
            if result.returncode != 0:
                claude_failed = True
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] claude 执行超过 {claude_timeout} 秒，强制终止")
            claude_failed = True
        except FileNotFoundError:
            print("  [ERROR] claude 命令未找到")
            return False
        except Exception as e:
            print(f"  [ERROR] 启动 claude 失败: {e}")
            claude_failed = True

        # 5. 对比进度
        progress_after = _get_progress(project_dir)
        delta = progress_after - progress_before
        print(f"  本次进展: +{delta} 个任务（{progress_before} → {progress_after}）")

        if delta == 0:
            no_progress_count += 1
            print(f"  [WARN] 连续 {no_progress_count} 次无进展")
        else:
            no_progress_count = 0

        # C4: 更新 session-state.json（consecutive_failures + last_test_results）
        _update_session_after_run(project_dir, claude_failed, delta)

        # 6. 无进展安全阀
        if no_progress_count >= no_progress_threshold:
            print(f"[SAFETY] 连续 {no_progress_threshold} 次重启无进展，停止")
            return False

        # 短暂等待后继续
        if restart < max_restarts - 1:
            print("  等待 5 秒后重启...")
            time.sleep(5)

    print(f"[LIMIT] 已达最大重启次数 {max_restarts}")
    # 最终检查
    if _check_all_tasks_pass(dev_state, iteration_id):
        print("[SUCCESS] 所有任务已 PASS")
        return True

    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AutoLoop 外围循环脚本 — 自动重启 Claude 会话直到任务完成"
    )
    parser.add_argument(
        "--project-dir",
        required=True,
        help="目标项目目录路径",
    )
    parser.add_argument(
        "--iteration-id",
        required=True,
        help="迭代编号（如 iter-1）",
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=10,
        help="最大重启次数（默认 10）",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(f"ERROR: 项目目录不存在: {project_dir}")
        sys.exit(1)

    success = run_auto_loop(project_dir, args.iteration_id, args.max_restarts)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
