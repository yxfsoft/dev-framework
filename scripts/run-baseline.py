#!/usr/bin/env python3
"""
run-baseline.py — 运行基线测试并记录结果

用法:
    python dev-framework/scripts/run-baseline.py \
        --project-dir "<项目路径>" \
        --iteration-id "iter-3"

执行后更新:
    .claude/dev-state/baseline.json
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加 scripts 目录到 path 以导入 fw_utils
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import validate_safe_id, detect_toolchain, load_run_config, build_test_cmd, build_lint_cmd, parse_pytest_output


def run_baseline(project_dir: Path, iteration_id: str) -> None:
    """运行基线测试"""
    project_dir = project_dir.resolve()
    dev_state = project_dir / ".claude" / "dev-state"

    if not dev_state.exists():
        print(f"错误: {dev_state} 不存在")
        return

    # 加载工具链配置
    config = load_run_config(project_dir)
    toolchain = detect_toolchain(project_dir, config)

    print(f"运行基线测试: {project_dir}")
    print(f"工具链: test_runner={toolchain['test_runner']}")
    print()

    # 获取当前 git commit
    git_result = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        capture_output=True,
        text=True,
        cwd=project_dir,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    git_commit = ""
    if git_result.returncode == 0 and git_result.stdout and git_result.stdout.strip():
        parts = git_result.stdout.strip().split(" ", 1)
        git_commit = parts[0] if parts else ""
    elif git_result.returncode != 0:
        print(f"  [WARN]  git log 命令失败（returncode={git_result.returncode}），跳过 git commit 记录")

    # 运行 L1 单元测试（M11: 从 config 读取 test_dir）
    print("[1/3] 运行 L1 单元测试...")
    test_dir_rel = (
        config.get("toolchain", {}).get("test_dir")
        or config.get("test_dir")
        or "tests/unit/"
    )
    unit_dir = project_dir / test_dir_rel
    if unit_dir.exists():
        l1_cmd = build_test_cmd(toolchain, test_dir_rel, ["-q", "--tb=no"])
        try:
            l1_result = subprocess.run(
                l1_cmd,
                capture_output=True,
                text=True,
                cwd=project_dir,
                timeout=600,
                encoding="utf-8",
                errors="replace",
            )
            l1_output = l1_result.stdout + l1_result.stderr
            l1_parsed = parse_pytest_output(l1_output)
            print(f"  L1: {l1_parsed['passed']} passed, {l1_parsed['failed']} failed, {l1_parsed['skipped']} skipped")
        except subprocess.TimeoutExpired:
            l1_parsed = {"passed": 0, "failed": 0, "skipped": 0}
            l1_output = ""
            print(f"  L1: 测试执行超时（>600s）")
    else:
        l1_parsed = {"passed": 0, "failed": 0, "skipped": 0}
        l1_output = ""
        print(f"  L1: N/A - 未找到测试目录 ({test_dir_rel})")

    # 运行 L2 集成测试
    print("[2/3] 运行 L2 集成测试...")
    l2_parsed = {"passed": 0, "failed": 0, "skipped": 0}
    integration_dir = project_dir / "tests" / "integration"
    if integration_dir.exists():
        l2_cmd = build_test_cmd(toolchain, "tests/integration/", ["-q", "--tb=no"])
        try:
            l2_result = subprocess.run(
                l2_cmd,
                capture_output=True,
                text=True,
                cwd=project_dir,
                timeout=600,
                encoding="utf-8",
                errors="replace",
            )
            l2_output = l2_result.stdout + l2_result.stderr
            l2_parsed = parse_pytest_output(l2_output)
            print(f"  L2: {l2_parsed['passed']} passed, {l2_parsed['failed']} failed")
        except subprocess.TimeoutExpired:
            l2_parsed = {"passed": 0, "failed": 0, "skipped": 0}
            print(f"  L2: 集成测试执行超时（>600s）")
    else:
        print("  L2: 跳过（无 tests/integration/ 目录）")

    # Lint 检查
    print("[3/3] Lint 检查...")
    lint_clean = True
    lint_cmd = build_lint_cmd(toolchain)
    try:
        lint_result = subprocess.run(
            lint_cmd,
            capture_output=True,
            text=True,
            cwd=project_dir,
            encoding="utf-8", errors="replace",
        )
        if lint_result.returncode != 0:
            lint_clean = False
            print("  Lint: 有问题")
        else:
            print("  Lint: 通过")
    except FileNotFoundError:
        print("  Lint: 跳过（lint 工具未安装）")

    # 收集预存失败（依赖 pytest 输出格式: "FAILED tests/path::test_name - reason"）
    pre_existing = []
    if l1_parsed["failed"] > 0 and unit_dir.exists():
        # 重新运行获取失败的测试名
        detail_cmd = build_test_cmd(toolchain, test_dir_rel, ["-q", "--tb=line"])
        detail_result = subprocess.run(
            detail_cmd,
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=600,
            encoding="utf-8", errors="replace",
        )
        for line in detail_result.stdout.split("\n"):
            if "FAILED" in line:
                # pytest 格式: "FAILED tests/path::test_name - reason"
                parts = line.strip().split(" ", 2)
                if len(parts) >= 2 and parts[0] == "FAILED":
                    test_name = parts[1].rstrip(" -")
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
            "l2_skipped": l2_parsed["skipped"],
        },
        "lint_clean": lint_clean,
        "pre_existing_failures": pre_existing,
    }
    if not unit_dir.exists():
        baseline["l1_note"] = f"N/A - 未找到测试目录 ({test_dir_rel})"

    baseline_path = dev_state / "baseline.json"
    baseline_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8")

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
    validate_safe_id(args.iteration_id, "iteration-id")
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"[ERROR] --project-dir 目录不存在: {project_dir}")
        sys.exit(1)
    run_baseline(project_dir, args.iteration_id)


if __name__ == "__main__":
    main()
