#!/usr/bin/env python3
"""
run-verify.py — 运行指定 CR 的验收脚本

用法:
    # 运行单个 CR 的验收
    python dev-framework/scripts/run-verify.py \
        --project-dir "D:/project" \
        --iteration-id "iter-3" \
        --task-id "CR-001"

    # 运行整个迭代的所有验收脚本
    python dev-framework/scripts/run-verify.py \
        --project-dir "D:/project" \
        --iteration-id "iter-3" \
        --all
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_single_verify(
    project_dir: Path, iteration_id: str, task_id: str
) -> bool:
    """运行单个 CR 的验收脚本"""
    verify_script = (
        project_dir
        / ".claude"
        / "dev-state"
        / iteration_id
        / "verify"
        / f"{task_id}.py"
    )

    if not verify_script.exists():
        print(f"  SKIP  {task_id}: verify 脚本不存在 ({verify_script})")
        return True  # 无脚本不阻塞

    print(f"\n{'='*40}")
    print(f"运行验收: {task_id}")
    print(f"脚本: {verify_script}")
    print(f"{'='*40}")

    result = subprocess.run(
        [sys.executable, str(verify_script)],
        capture_output=True,
        text=True,
        cwd=project_dir,
        timeout=120,
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode == 0:
        # 更新任务文件中的 acceptance_criteria 状态
        update_task_criteria(project_dir, iteration_id, task_id, passed=True)
        return True
    else:
        update_task_criteria(project_dir, iteration_id, task_id, passed=False)
        return False


def update_task_criteria(
    project_dir: Path, iteration_id: str, task_id: str, passed: bool
) -> None:
    """更新任务文件中的验收状态（简化版，仅标记整体状态）"""
    # 注意：完整实现应解析 verify 脚本输出，逐条更新 criteria
    # 这里是简化版，仅在日志中记录
    status = "PASS" if passed else "FAIL"
    print(f"\n  验收结果: {task_id} = {status}")


def run_all_verify(project_dir: Path, iteration_id: str) -> None:
    """运行整个迭代的所有验收脚本"""
    verify_dir = (
        project_dir / ".claude" / "dev-state" / iteration_id / "verify"
    )

    if not verify_dir.exists():
        print(f"错误: {verify_dir} 不存在")
        return

    scripts = sorted(verify_dir.glob("*.py"))
    if not scripts:
        print("无验收脚本")
        return

    print(f"运行 {len(scripts)} 个验收脚本")

    results = []
    for script in scripts:
        task_id = script.stem
        passed = run_single_verify(project_dir, iteration_id, task_id)
        results.append((task_id, passed))

    # 汇总
    print(f"\n{'='*50}")
    passed_count = sum(1 for _, p in results if p)
    total = len(results)
    print(f"验收汇总: {passed_count}/{total} PASS")
    for task_id, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}  {task_id}")

    if passed_count < total:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="运行验收脚本")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument("--iteration-id", required=True, help="迭代 ID")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task-id", help="单个任务 ID")
    group.add_argument("--all", action="store_true", help="运行所有验收脚本")

    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    if args.all:
        run_all_verify(project_dir, args.iteration_id)
    else:
        passed = run_single_verify(project_dir, args.iteration_id, args.task_id)
        if not passed:
            sys.exit(1)


if __name__ == "__main__":
    main()
