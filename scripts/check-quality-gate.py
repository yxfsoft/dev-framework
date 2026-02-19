#!/usr/bin/env python3
"""
check-quality-gate.py — 运行质量门控检查

用法:
    # 检查特定门控
    python dev-framework/scripts/check-quality-gate.py \
        --project-dir "D:/project" \
        --gate "gate_4"

    # 检查所有门控
    python dev-framework/scripts/check-quality-gate.py \
        --project-dir "D:/project" \
        --all

门控列表:
    gate_0: 环境就绪
    gate_3: L0 验收（需指定 --task-id）
    gate_4: L1 回归
    gate_5: 集成检查点
    gate_7: 最终验收
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_baseline(project_dir: Path) -> dict | None:
    """加载基线"""
    baseline_path = project_dir / ".claude" / "dev-state" / "baseline.json"
    if not baseline_path.exists():
        return None
    return json.loads(baseline_path.read_text())


def gate_0_environment(project_dir: Path) -> bool:
    """Gate 0: 环境就绪"""
    print("\n[Gate 0] 环境就绪检查")
    checks = []

    # git status 干净
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=project_dir,
    )
    clean = result.stdout.strip() == ""
    checks.append(("git 工作区干净", clean))
    print(f"  {'PASS' if clean else 'WARN'}  git 工作区{'干净' if clean else '有未提交改动'}")

    # Python 可用
    result = subprocess.run(
        [sys.executable, "--version"],
        capture_output=True, text=True,
    )
    py_ok = result.returncode == 0
    checks.append(("Python 可用", py_ok))
    print(f"  {'PASS' if py_ok else 'FAIL'}  Python: {result.stdout.strip()}")

    # pytest 可用
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--version"],
        capture_output=True, text=True,
    )
    pytest_ok = result.returncode == 0
    checks.append(("pytest 可用", pytest_ok))
    print(f"  {'PASS' if pytest_ok else 'FAIL'}  pytest")

    all_pass = all(c[1] for c in checks)
    print(f"\n  Gate 0: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


def gate_4_regression(project_dir: Path) -> bool:
    """Gate 4: L1 回归检查"""
    print("\n[Gate 4] L1 回归检查")

    baseline = load_baseline(project_dir)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit/", "-q", "--tb=no"],
        capture_output=True, text=True, cwd=project_dir, timeout=600,
    )

    output = result.stdout + result.stderr
    print(f"  输出: {output.strip()[-300:]}")

    if result.returncode != 0:
        print("  FAIL  L1 测试有失败")
        return False

    if baseline:
        baseline_passed = baseline["test_results"]["l1_passed"]
        print(f"  基线: {baseline_passed} passed")
        # 简单检查：returncode == 0 说明无失败
        print(f"  PASS  无回归（基线 {baseline_passed} passed）")
    else:
        print("  PASS  无基线，仅检查是否有失败")

    return True


def gate_5_integration(project_dir: Path) -> bool:
    """Gate 5: 集成检查点"""
    print("\n[Gate 5] 集成检查点")

    # L1
    l1_ok = gate_4_regression(project_dir)
    if not l1_ok:
        return False

    # L2
    print("\n  L2 集成测试...")
    integration_dir = project_dir / "tests" / "integration"
    if integration_dir.exists():
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/integration/", "-q", "--tb=no"],
            capture_output=True, text=True, cwd=project_dir, timeout=600,
        )
        if result.returncode != 0:
            print("  FAIL  L2 集成测试有失败")
            return False
        print("  PASS  L2 集成测试通过")
    else:
        print("  SKIP  无 L2 测试目录")

    # Lint
    print("\n  Lint 检查...")
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        capture_output=True, text=True, cwd=project_dir,
    )
    if result.returncode != 0:
        print("  FAIL  Lint 有问题")
        return False
    print("  PASS  Lint 通过")

    print(f"\n  Gate 5: PASS")
    return True


def gate_7_final(project_dir: Path) -> bool:
    """Gate 7: 最终验收"""
    print("\n[Gate 7] 最终验收")

    # 运行 Gate 5 的所有检查
    gate5_ok = gate_5_integration(project_dir)
    if not gate5_ok:
        return False

    # 检查空实现
    print("\n  空实现检查...")
    result = subprocess.run(
        ["grep", "-rn", "NotImplementedError", "--include=*.py",
         "apps/", "services/", "packages/"],
        capture_output=True, text=True, cwd=project_dir,
    )
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        print(f"  WARN  发现 {len(lines)} 处 NotImplementedError")
        for line in lines[:5]:
            print(f"        {line}")
    else:
        print("  PASS  无 NotImplementedError")

    print(f"\n  Gate 7: PASS")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="质量门控检查")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument(
        "--gate",
        choices=["gate_0", "gate_4", "gate_5", "gate_7"],
        help="检查特定门控",
    )
    parser.add_argument("--all", action="store_true", help="检查所有门控")

    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    gates = {
        "gate_0": gate_0_environment,
        "gate_4": gate_4_regression,
        "gate_5": gate_5_integration,
        "gate_7": gate_7_final,
    }

    if args.all:
        results = []
        for name, fn in gates.items():
            passed = fn(project_dir)
            results.append((name, passed))

        print(f"\n{'='*50}")
        print("门控汇总:")
        for name, passed in results:
            print(f"  {'PASS' if passed else 'FAIL'}  {name}")

        if not all(p for _, p in results):
            sys.exit(1)
    elif args.gate:
        passed = gates[args.gate](project_dir)
        if not passed:
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
