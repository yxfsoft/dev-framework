#!/usr/bin/env python3
"""
check-quality-gate.py — 运行质量门控检查

用法:
    # 检查特定门控
    python dev-framework/scripts/check-quality-gate.py \
        --project-dir "D:/project" \
        --gate "gate_4"

    # 检查特定门控（Gate 3 需指定 --iteration-id 和 --task-id）
    python dev-framework/scripts/check-quality-gate.py \
        --project-dir "D:/project" \
        --gate "gate_3" \
        --iteration-id "iter-3" \
        --task-id "CR-001"

    # 检查所有门控（跳过需要额外参数的 gate_3/gate_6）
    python dev-framework/scripts/check-quality-gate.py \
        --project-dir "D:/project" \
        --all

门控列表:
    gate_0: 环境就绪
    gate_1: 需求审批（检查 requirement-spec.md 是否存在）
    gate_2: 任务拆分审批（检查 CR 文件和 verify 脚本完整性）
    gate_3: L0 验收（调用 run-verify.py，需指定 --iteration-id 和 --task-id）
    gate_4: L1 回归
    gate_5: 集成检查点
    gate_6: 代码审查（检查任务的 review_result 字段）
    gate_7: 最终验收
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def load_baseline(project_dir: Path) -> "dict | None":
    """加载基线"""
    baseline_path = project_dir / ".claude" / "dev-state" / "baseline.json"
    if not baseline_path.exists():
        return None
    return json.loads(baseline_path.read_text())


def parse_pytest_passed(output: str) -> int:
    """从 pytest 输出中解析 passed 数量"""
    match = re.search(r"(\d+) passed", output)
    return int(match.group(1)) if match else 0


def gate_0_environment(project_dir: Path, **kwargs) -> bool:
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


def gate_1_requirement(project_dir: Path, **kwargs) -> bool:
    """Gate 1: 需求审批（检查 requirement-spec.md 是否存在且完整）"""
    print("\n[Gate 1] 需求审批检查")
    iteration_id = kwargs.get("iteration_id")

    if not iteration_id:
        # 尝试从 session-state.json 读取
        state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            iteration_id = state.get("current_iteration")

    if not iteration_id:
        print("  SKIP  未指定 iteration-id，且无法从 session-state.json 读取")
        print("  提示: Gate 1 需要人工确认需求规格书，此处仅检查文件是否存在")
        return True

    spec_path = (
        project_dir / ".claude" / "dev-state" / iteration_id / "requirement-spec.md"
    )
    if spec_path.exists():
        content = spec_path.read_text(encoding="utf-8")
        print(f"  PASS  requirement-spec.md 存在 ({len(content)} 字符)")
    else:
        print(f"  WARN  requirement-spec.md 不存在: {spec_path}")
        print("  提示: Gate 1 主要依赖人工确认，此检查仅为辅助")

    print(f"\n  Gate 1: PASS (需人工确认)")
    return True


def gate_2_task_plan(project_dir: Path, **kwargs) -> bool:
    """Gate 2: 任务拆分审批（结构化校验 + 人工确认）"""
    print("\n[Gate 2] 任务拆分审批检查")
    iteration_id = kwargs.get("iteration_id")

    if not iteration_id:
        state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            iteration_id = state.get("current_iteration")

    if not iteration_id:
        print("  SKIP  未指定 iteration-id")
        return True

    iter_dir = project_dir / ".claude" / "dev-state" / iteration_id
    tasks_dir = iter_dir / "tasks"
    verify_dir = iter_dir / "verify"
    errors: list[str] = []

    if not tasks_dir.exists() or not list(tasks_dir.glob("*.yaml")):
        errors.append("tasks 目录为空或不存在")
    else:
        try:
            import yaml
        except ImportError:
            print("  WARN  PyYAML 未安装，跳过结构化校验")
            print(f"\n  Gate 2: PASS (需人工确认)")
            return True

        verify_files = {f.stem for f in verify_dir.glob("*.py")} if verify_dir.exists() else set()
        task_files = sorted(tasks_dir.glob("*.yaml"))
        print(f"  任务文件: {len(task_files)} 个")
        print(f"  验收脚本: {len(verify_files)} 个")

        for tf in task_files:
            try:
                task = yaml.safe_load(tf.read_text(encoding="utf-8"))
            except Exception:
                errors.append(f"{tf.stem}: YAML 解析失败")
                continue
            if not task:
                continue
            tid = task.get("id", tf.stem)

            # affected_files ≤ 5
            af = task.get("affected_files", [])
            if len(af) > 5:
                errors.append(f"{tid}: affected_files={len(af)} > 5")

            # acceptance_criteria 非空（兼容新旧格式）
            ac = task.get("acceptance_criteria")
            if isinstance(ac, dict):
                func_ac = ac.get("functional", [])
                if len(func_ac) < 1:
                    errors.append(f"{tid}: acceptance_criteria.functional 为空")
            elif isinstance(ac, list):
                if len(ac) < 1:
                    errors.append(f"{tid}: acceptance_criteria 为空")
            else:
                errors.append(f"{tid}: acceptance_criteria 缺失")

            # design.why_this_approach 非空
            design = task.get("design", {})
            if not design.get("why_this_approach", "").strip():
                errors.append(f"{tid}: design 缺少 why_this_approach")

            # 对应 verify 脚本存在
            if tid not in verify_files:
                errors.append(f"{tid}: 缺少 verify/{tid}.py")

    if errors:
        print(f"  FAIL  结构化校验发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"        {e}")
        print(f"\n  Gate 2: FAIL")
        return False

    print(f"  PASS  结构化校验通过")
    print(f"\n  Gate 2: PASS (需人工确认任务拆分方案)")
    return True


def gate_3_l0_verify(project_dir: Path, **kwargs) -> bool:
    """Gate 3: L0 验收（调用 run-verify.py）"""
    print("\n[Gate 3] L0 验收检查")
    iteration_id = kwargs.get("iteration_id")
    task_id = kwargs.get("task_id")

    if not iteration_id or not task_id:
        print("  FAIL  Gate 3 需要 --iteration-id 和 --task-id 参数")
        return False

    # 调用 run-verify.py
    script_path = Path(__file__).parent / "run-verify.py"
    if not script_path.exists():
        print(f"  FAIL  验收脚本不存在: {script_path}")
        return False
    result = subprocess.run(
        [
            sys.executable, str(script_path),
            "--project-dir", str(project_dir),
            "--iteration-id", iteration_id,
            "--task-id", task_id,
        ],
        capture_output=True, text=True, cwd=project_dir, timeout=120,
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    passed = result.returncode == 0
    print(f"\n  Gate 3: {'PASS' if passed else 'FAIL'}")
    return passed


def gate_4_regression(project_dir: Path, **kwargs) -> bool:
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

    # 解析实际 passed 数与基线比较
    current_passed = parse_pytest_passed(output)

    if baseline:
        baseline_passed = baseline["test_results"]["l1_passed"]
        print(f"  基线: {baseline_passed} passed")
        print(f"  当前: {current_passed} passed")
        if current_passed < baseline_passed:
            print(f"  FAIL  测试数量下降: {current_passed} < {baseline_passed} (可能有测试被删除)")
            return False
        print(f"  PASS  无回归（基线 {baseline_passed}, 当前 {current_passed}）")
    else:
        print(f"  PASS  无基线，仅检查是否有失败（当前 {current_passed} passed）")

    return True


def gate_5_integration(project_dir: Path, **kwargs) -> bool:
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

    # Mock 合规
    mock_ok = check_mock_compliance(project_dir)
    if not mock_ok:
        return False

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


def gate_6_code_review(project_dir: Path, **kwargs) -> bool:
    """Gate 6: 代码审查（检查任务的 review_result 字段）"""
    print("\n[Gate 6] 代码审查检查")
    iteration_id = kwargs.get("iteration_id")
    task_id = kwargs.get("task_id")

    if not iteration_id:
        state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            iteration_id = state.get("current_iteration")

    if not iteration_id:
        print("  SKIP  未指定 iteration-id")
        return True

    tasks_dir = project_dir / ".claude" / "dev-state" / iteration_id / "tasks"
    if not tasks_dir.exists():
        print(f"  WARN  任务目录不存在: {tasks_dir}")
        return True

    try:
        import yaml
    except ImportError:
        print("  WARN  PyYAML 未安装，无法解析任务文件")
        print("  提示: pip install PyYAML")
        return True

    # 如果指定了 task_id，只检查该任务；否则检查所有 ready_for_review 的任务
    if task_id:
        task_files = [tasks_dir / f"{task_id}.yaml"]
    else:
        task_files = sorted(tasks_dir.glob("*.yaml"))

    reviewed = 0
    not_reviewed = 0
    for tf in task_files:
        if not tf.exists():
            continue
        try:
            task = yaml.safe_load(tf.read_text(encoding="utf-8"))
            if not task:
                continue
        except Exception as e:
            print(f"  WARN  解析 {tf.name} 失败: {e}", file=sys.stderr)
            continue

        status = task.get("status", "")
        if status not in ("ready_for_review", "PASS"):
            continue

        review_result = task.get("review_result")
        tid = task.get("id", tf.stem)
        if review_result and review_result.get("verdict") == "PASS":
            print(f"  PASS  {tid}: Reviewer 已 PASS")
            reviewed += 1
        elif review_result and review_result.get("verdict") == "REWORK":
            print(f"  FAIL  {tid}: Reviewer 判定 REWORK")
            not_reviewed += 1
        elif status == "ready_for_review":
            print(f"  WAIT  {tid}: 等待 Reviewer 审查")
            not_reviewed += 1

    if not_reviewed > 0:
        print(f"\n  Gate 6: FAIL ({not_reviewed} 个任务未通过审查)")
        return False

    print(f"\n  Gate 6: PASS ({reviewed} 个任务已审查通过)")
    return True


def check_mock_compliance(project_dir: Path) -> bool:
    """扫描测试文件中的 Mock 使用，要求非白名单 Mock 必须声明 # MOCK-REASON:"""
    print("\n  Mock 合规检查...")
    mock_pattern = re.compile(r"\b(mock|Mock|MagicMock|patch|mocker)\b")
    reason_pattern = re.compile(r"#\s*MOCK-REASON:\s*.+")
    violations: list[str] = []

    tests_dir = project_dir / "tests"
    if not tests_dir.exists():
        print("  SKIP  无 tests 目录")
        return True

    for py_file in tests_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if mock_pattern.search(content) and not reason_pattern.search(content):
            violations.append(str(py_file.relative_to(project_dir)))

    if violations:
        print(f"  FAIL  {len(violations)} 个测试文件使用 Mock 但未声明 # MOCK-REASON:")
        for v in violations[:5]:
            print(f"        {v}")
        if len(violations) > 5:
            print(f"        ... 还有 {len(violations) - 5} 个")
        return False
    print("  PASS  Mock 使用合规")
    return True


def gate_7_final(project_dir: Path, **kwargs) -> bool:
    """Gate 7: 最终验收"""
    print("\n[Gate 7] 最终验收")

    # 运行 Gate 5 的所有检查
    gate5_ok = gate_5_integration(project_dir)
    if not gate5_ok:
        return False

    # 检查空实现（跨平台兼容：使用 Python 原生实现替代 grep）
    print("\n  空实现检查...")
    not_impl_found = []
    for py_file in project_dir.rglob("*.py"):
        # 跳过虚拟环境、缓存、隐藏目录
        parts = py_file.parts
        if any(p.startswith(".") or p in ("__pycache__", "node_modules", ".venv", "venv") for p in parts):
            continue
        try:
            with open(py_file, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if "NotImplementedError" in line:
                        rel_path = py_file.relative_to(project_dir)
                        not_impl_found.append(f"{rel_path}:{i}: {line.strip()}")
        except OSError:
            continue

    if not_impl_found:
        print(f"  FAIL  发现 {len(not_impl_found)} 处 NotImplementedError（禁止空实现）")
        for entry in not_impl_found[:5]:
            print(f"        {entry}")
        if len(not_impl_found) > 5:
            print(f"        ... 还有 {len(not_impl_found) - 5} 处")
        print(f"\n  Gate 7: FAIL")
        return False
    else:
        print("  PASS  无 NotImplementedError")

    print(f"\n  Gate 7: PASS")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="质量门控检查")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument(
        "--gate",
        choices=["gate_0", "gate_1", "gate_2", "gate_3", "gate_4", "gate_5", "gate_6", "gate_7"],
        help="检查特定门控",
    )
    parser.add_argument("--iteration-id", help="迭代 ID（gate_3/gate_6 需要）")
    parser.add_argument("--task-id", help="任务 ID（gate_3 需要）")
    parser.add_argument("--all", action="store_true", help="检查所有门控（跳过需要额外参数的 gate_3）")

    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    extra = {
        "iteration_id": args.iteration_id,
        "task_id": args.task_id,
    }

    gates = {
        "gate_0": gate_0_environment,
        "gate_1": gate_1_requirement,
        "gate_2": gate_2_task_plan,
        "gate_3": gate_3_l0_verify,
        "gate_4": gate_4_regression,
        "gate_5": gate_5_integration,
        "gate_6": gate_6_code_review,
        "gate_7": gate_7_final,
    }

    if args.all:
        results = []
        for name, fn in gates.items():
            # gate_3 需要 task-id，--all 模式下跳过
            if name == "gate_3" and not args.task_id:
                print(f"\n  SKIP  {name}（需要 --task-id 参数）")
                results.append((name, True))
                continue
            passed = fn(project_dir, **extra)
            results.append((name, passed))

        print(f"\n{'='*50}")
        print("门控汇总:")
        for name, passed in results:
            print(f"  {'PASS' if passed else 'FAIL'}  {name}")

        if not all(p for _, p in results):
            sys.exit(1)
    elif args.gate:
        passed = gates[args.gate](project_dir, **extra)
        if not passed:
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
