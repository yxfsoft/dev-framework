#!/usr/bin/env python3
"""
run-baseline.py — 运行基线测试并记录结果

用法:
    python dev-framework/scripts/run-baseline.py \
        --project-dir "D:/existing-project" \
        --iteration-id "iter-3"

执行后更新:
    .claude/dev-state/baseline.json
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_pytest_output(output: str) -> dict:
    """解析 pytest 输出，提取 passed/failed/skipped 数量"""
    result = {"passed": 0, "failed": 0, "skipped": 0}

    # 匹配 pytest 汇总行: "X passed, Y failed, Z skipped"
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


def run_baseline(project_dir: Path, iteration_id: str) -> None:
    """运行基线测试"""
    project_dir = project_dir.resolve()
    dev_state = project_dir / ".claude" / "dev-state"

    if not dev_state.exists():
        print(f"错误: {dev_state} 不存在")
        return

    print(f"运行基线测试: {project_dir}")
    print()

    # 获取当前 git commit
    git_result = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    git_commit = git_result.stdout.strip().split(" ")[0] if git_result.returncode == 0 else ""

    # 运行 L1 单元测试
    print("[1/3] 运行 L1 单元测试...")
    l1_result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit/", "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=project_dir,
        timeout=600,
    )
    l1_output = l1_result.stdout + l1_result.stderr
    l1_parsed = parse_pytest_output(l1_output)
    print(f"  L1: {l1_parsed['passed']} passed, {l1_parsed['failed']} failed, {l1_parsed['skipped']} skipped")

    # 运行 L2 集成测试
    print("[2/3] 运行 L2 集成测试...")
    l2_parsed = {"passed": 0, "failed": 0, "skipped": 0}
    integration_dir = project_dir / "tests" / "integration"
    if integration_dir.exists():
        l2_result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/integration/", "-q", "--tb=no"],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=600,
        )
        l2_output = l2_result.stdout + l2_result.stderr
        l2_parsed = parse_pytest_output(l2_output)
        print(f"  L2: {l2_parsed['passed']} passed, {l2_parsed['failed']} failed")
    else:
        print("  L2: 跳过（无 tests/integration/ 目录）")

    # Lint 检查
    print("[3/3] Lint 检查...")
    lint_clean = True
    lint_result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    if lint_result.returncode != 0:
        lint_clean = False
        print(f"  Lint: 有问题")
    else:
        print(f"  Lint: 通过")

    # 收集预存失败
    pre_existing = []
    if l1_parsed["failed"] > 0:
        # 重新运行获取失败的测试名
        detail_result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/unit/", "-q", "--tb=line", "-x"],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=600,
        )
        for line in detail_result.stdout.split("\n"):
            if "FAILED" in line:
                test_name = line.split(" ")[0].replace("FAILED", "").strip()
                if test_name:
                    pre_existing.append(test_name)

    # 写入 baseline.json
    baseline = {
        "iteration": iteration_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "test_results": {
            "l1_passed": l1_parsed["passed"],
            "l1_failed": l1_parsed["failed"],
            "l1_skipped": l1_parsed["skipped"],
            "l2_passed": l2_parsed["passed"],
            "l2_failed": l2_parsed["failed"],
        },
        "lint_clean": lint_clean,
        "pre_existing_failures": pre_existing,
    }

    baseline_path = dev_state / "baseline.json"
    baseline_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False))

    print()
    print("=" * 50)
    print(f"基线已记录: {baseline_path}")
    print(f"  L1: {l1_parsed['passed']} passed")
    print(f"  L2: {l2_parsed['passed']} passed")
    print(f"  Lint: {'通过' if lint_clean else '有问题'}")
    if pre_existing:
        print(f"  预存失败: {len(pre_existing)} 个")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行基线测试")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument("--iteration-id", required=True, help="迭代 ID")
    args = parser.parse_args()
    run_baseline(Path(args.project_dir), args.iteration_id)


if __name__ == "__main__":
    main()
