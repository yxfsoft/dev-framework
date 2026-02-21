#!/usr/bin/env python3
"""
check-quality-gate.py — 运行质量门控检查

用法:
    # 检查特定门控
    python dev-framework/scripts/check-quality-gate.py \
        --project-dir "<项目路径>" \
        --gate "gate_4"

    # 检查特定门控（Gate 3 需指定 --iteration-id 和 --task-id）
    python dev-framework/scripts/check-quality-gate.py \
        --project-dir "<项目路径>" \
        --gate "gate_3" \
        --iteration-id "iter-3" \
        --task-id "CR-001"

    # 检查所有门控（跳过需要额外参数的 gate_3/gate_6）
    python dev-framework/scripts/check-quality-gate.py \
        --project-dir "<项目路径>" \
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

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# 目录遍历时需要跳过的常见非项目目录
# 仅用于 gate_7 的 os.walk 遍历（空实现检查 NotImplementedError），其他 Gate 不使用此集合
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build"}

# 检查结果缓存（同一次 main() 调用内避免重复执行相同检查）
_check_cache: dict = {}

# 添加 scripts 目录到 path 以导入 fw_utils
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import (
    load_baseline, parse_pytest_passed, detect_toolchain,
    load_run_config, build_test_cmd, build_lint_cmd,
)


def gate_0_environment(project_dir: Path, **kwargs) -> bool:
    """Gate 0: 环境就绪"""
    print("\n[Gate 0] 环境就绪检查")
    checks = []

    config = load_run_config(project_dir)
    toolchain = detect_toolchain(project_dir, config)

    # git status 干净（git 工作区不干净不阻断 Gate 0，仅作为 WARN 提示）
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=project_dir,
        encoding="utf-8", errors="replace",
    )
    clean = result.stdout.strip() == ""
    print(f"  {'PASS' if clean else 'WARN'}  git 工作区{'干净' if clean else '有未提交改动'}")

    # Python 可用
    result = subprocess.run(
        [sys.executable, "--version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    py_ok = result.returncode == 0
    checks.append(("Python 可用", py_ok))
    print(f"  {'PASS' if py_ok else 'FAIL'}  Python: {result.stdout.strip()}")

    # pytest 可用（通过工具链检测）
    import shlex
    test_cmd = shlex.split(toolchain["test_runner"])
    result = subprocess.run(
        test_cmd + ["--version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    pytest_ok = result.returncode == 0
    checks.append(("pytest 可用", pytest_ok))
    print(f"  {'PASS' if pytest_ok else 'FAIL'}  pytest (via {toolchain['test_runner']})")

    # 基线检查（WARN，不影响 all_pass）
    baseline = load_baseline(project_dir)
    if baseline and baseline.get("git_commit", "") == "":
        print("  WARN  基线尚未运行（git_commit 为空），建议先运行 run-baseline.py")

    all_pass = all(c[1] for c in checks)
    print(f"\n  Gate 0: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


def gate_1_requirement(project_dir: Path, **kwargs) -> bool | str:
    """Gate 1: 需求审批（检查 requirement-spec.md 是否存在且完整）"""
    print("\n[Gate 1] 需求审批检查")
    iteration_id = kwargs.get("iteration_id")

    if not iteration_id:
        # 尝试从 session-state.json 读取
        state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            iteration_id = state.get("current_iteration")

    if not iteration_id:
        print("  SKIP  未指定 iteration-id，且无法从 session-state.json 读取（请手动指定 --iteration-id）")
        print("  提示: Gate 1 需要人工确认需求规格书，此处仅检查文件是否存在")
        print("\n  Gate 1: SKIP（非 PASS，因缺少 iteration-id 跳过检查。请手动确认需求规格书。）")
        return "SKIP"

    spec_path = (
        project_dir / ".claude" / "dev-state" / iteration_id / "requirement-spec.md"
    )
    if spec_path.exists():
        content = spec_path.read_text(encoding="utf-8")
        print(f"  PASS  requirement-spec.md 存在 ({len(content)} 字符)")
        print(f"\n  Gate 1: PASS (需人工确认)")
        return True
    else:
        print(f"  FAIL  requirement-spec.md 不存在: {spec_path}")
        print("  提示: 需先完成 Phase 1 需求深化，生成 requirement-spec.md")
        print(f"\n  Gate 1: FAIL")
        return False


def gate_2_task_plan(project_dir: Path, **kwargs) -> bool:
    """Gate 2: 任务拆分审批（结构化校验 + 人工确认）"""
    print("\n[Gate 2] 任务拆分审批检查")
    iteration_id = kwargs.get("iteration_id")

    if not iteration_id:
        state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
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
            print("  FAIL  PyYAML 未安装，无法执行结构化校验")
            print("  提示: pip install PyYAML")
            print(f"\n  Gate 2: FAIL")
            return False

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

            # hotfix 类型走简化流程，跳过结构化校验
            task_type = task.get("type", "")
            if task_type == "hotfix":
                continue

            # affected_files ≤ 5
            af = task.get("affected_files", [])
            if len(af) > 5:
                errors.append(f"{tid}: affected_files={len(af)} > 5")

            # acceptance_criteria 非空（仅支持 dict 格式，按维度分组）
            ac = task.get("acceptance_criteria")
            if isinstance(ac, dict):
                func_ac = ac.get("functional", [])
                if len(func_ac) < 1:
                    errors.append(f"{tid}: acceptance_criteria.functional 为空")
            else:
                errors.append(f"{tid}: acceptance_criteria 缺失或格式不正确（需要 dict）")

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
        encoding="utf-8", errors="replace",
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
    passed = _run_l1_regression(project_dir)
    print(f"\n  Gate 4: {'PASS' if passed else 'FAIL'}")
    return passed


def _run_l1_regression(project_dir: Path) -> bool:
    """运行 L1 单元测试并与基线对比（公共函数，供 gate_4/gate_5/gate_7 复用）。"""
    cache_key = ("l1_regression", str(project_dir))
    if cache_key in _check_cache:
        print("  (使用缓存结果)")
        return _check_cache[cache_key]
    baseline = load_baseline(project_dir)
    config = load_run_config(project_dir)
    toolchain = detect_toolchain(project_dir, config)

    # 从 run-config.yaml 读取测试目录，默认回退 "tests/unit/"
    test_dir = config.get("toolchain", {}).get("test_dir", config.get("test_dir", "tests/unit/"))
    test_cmd = build_test_cmd(toolchain, test_dir, ["-q", "--tb=no"])
    result = subprocess.run(
        test_cmd,
        capture_output=True, text=True, cwd=project_dir, timeout=600,
        encoding="utf-8", errors="replace",
    )

    output = result.stdout + result.stderr
    print(f"  输出: {output.strip()[-300:]}")

    if result.returncode != 0:
        print("  FAIL  L1 测试有失败")
        _check_cache[cache_key] = False
        return False

    current_passed = parse_pytest_passed(output)

    if baseline:
        baseline_passed = baseline["test_results"]["l1_passed"]
        print(f"  基线: {baseline_passed} passed")
        print(f"  当前: {current_passed} passed")
        if current_passed < baseline_passed:
            print(f"  FAIL  测试数量下降: {current_passed} < {baseline_passed} (可能有测试被删除)")
            _check_cache[cache_key] = False
            return False
        print(f"  PASS  无回归（基线 {baseline_passed}, 当前 {current_passed}）")
    else:
        print(f"  PASS  无基线，仅检查是否有失败（当前 {current_passed} passed）")

    _check_cache[cache_key] = True
    return True


def _run_l2_integration(project_dir: Path) -> bool:
    """运行 L2 集成测试（公共函数，供 gate_5/gate_7 复用）。"""
    cache_key = ("l2_integration", str(project_dir))
    if cache_key in _check_cache:
        print("\n  L2 集成测试... (使用缓存结果)")
        return _check_cache[cache_key]
    print("\n  L2 集成测试...")
    config = load_run_config(project_dir)
    toolchain = detect_toolchain(project_dir, config)
    integration_dir = project_dir / "tests" / "integration"
    if integration_dir.exists():
        l2_cmd = build_test_cmd(toolchain, "tests/integration/", ["-q", "--tb=no"])
        result = subprocess.run(
            l2_cmd,
            capture_output=True, text=True, cwd=project_dir, timeout=600,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            print("  FAIL  L2 集成测试有失败")
            _check_cache[cache_key] = False
            return False
        print("  PASS  L2 集成测试通过")
    else:
        print("  SKIP  无 L2 测试目录")
    _check_cache[cache_key] = True
    return True


def _run_lint(project_dir: Path) -> bool:
    """运行 Lint 检查（公共函数，供 gate_5/gate_7 复用）。"""
    cache_key = ("lint", str(project_dir))
    if cache_key in _check_cache:
        print("\n  Lint 检查... (使用缓存结果)")
        return _check_cache[cache_key]
    print("\n  Lint 检查...")
    config = load_run_config(project_dir)
    toolchain = detect_toolchain(project_dir, config)
    lint_cmd = build_lint_cmd(toolchain)
    try:
        result = subprocess.run(
            lint_cmd,
            capture_output=True, text=True, cwd=project_dir,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            print("  FAIL  Lint 有问题")
            _check_cache[cache_key] = False
            return False
        print("  PASS  Lint 通过")
    except FileNotFoundError:
        lint_required = config.get("toolchain", {}).get("lint_required", False)
        if lint_required:
            print("  FAIL  Lint 工具未安装（lint_required=true）")
            _check_cache[cache_key] = False
            return False
        print("  SKIP  Lint 工具未安装（lint_required=false，非强制）")
        print(f"  ⚠ WARNING: lint 工具未找到，此检查被 SKIP（非 PASS）。")
        print(f"  提示: 可在 run-config.yaml 的 toolchain.linter 中配置 lint 命令")
        print(f"  提示: 设置 toolchain.lint_required=true 可将此检查变为强制")
    _check_cache[cache_key] = True
    return True


def gate_5_integration(project_dir: Path, **kwargs) -> bool:
    """Gate 5: 集成检查点"""
    print("\n[Gate 5] 集成检查点")

    if not _run_l1_regression(project_dir):
        return False
    if not _run_l2_integration(project_dir):
        return False
    if not check_mock_compliance(project_dir):
        return False
    if not _run_lint(project_dir):
        return False

    # TODO/FIXME 扫描（WARN，不阻断 Gate 5）
    print("\n  TODO/FIXME 扫描...")
    try:
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            capture_output=True, text=True, cwd=project_dir,
            encoding="utf-8", errors="replace",
        )
        changed_files = [f for f in diff_result.stdout.strip().splitlines() if f.endswith(".py")]
    except Exception:
        changed_files = []
    todo_warnings: list[str] = []
    for fname in changed_files:
        fpath = project_dir / fname
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if "TODO" in line or "FIXME" in line:
                        todo_warnings.append(f"{fname}:{i}: {line.strip()}")
        except OSError:
            continue
    if todo_warnings:
        print(f"  WARN  发现 {len(todo_warnings)} 处 TODO/FIXME：")
        for entry in todo_warnings[:10]:
            print(f"        {entry}")
        if len(todo_warnings) > 10:
            print(f"        ... 还有 {len(todo_warnings) - 10} 处")
    else:
        print("  PASS  无 TODO/FIXME")

    print(f"\n  Gate 5: PASS")
    return True


def gate_6_code_review(project_dir: Path, **kwargs) -> bool | str:
    """Gate 6: 代码审查（检查任务的 review_result 字段）"""
    print("\n[Gate 6] 代码审查检查")
    iteration_id = kwargs.get("iteration_id")
    task_id = kwargs.get("task_id")

    if not iteration_id:
        state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            iteration_id = state.get("current_iteration")

    if not iteration_id:
        print("  SKIP  未指定 iteration-id")
        print("\n  Gate 6: SKIP（非 PASS，因缺少 iteration-id 跳过检查。请手动确认代码审查状态。）")
        return "SKIP"

    tasks_dir = project_dir / ".claude" / "dev-state" / iteration_id / "tasks"
    if not tasks_dir.exists():
        print(f"  WARN  任务目录不存在: {tasks_dir}")
        return True

    try:
        import yaml
    except ImportError:
        print("  FAIL  PyYAML 未安装，无法解析任务文件")
        print("  提示: pip install PyYAML")
        print(f"\n  Gate 6: FAIL")
        return False

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
    """扫描测试文件中的 Mock 使用，检查三项声明完整性。

    要求每个 Mock 必须同时包含：
    1. # MOCK-REASON: — Mock 存在的原因
    2. # MOCK-REAL-TEST: — 对应的真实测试路径（必须存在）
    3. # MOCK-EXPIRE-WHEN: — Mock 的移除条件
    """
    cache_key = ("mock_compliance", str(project_dir))
    if cache_key in _check_cache:
        print("\n  Mock 合规检查... (使用缓存结果)")
        return _check_cache[cache_key]
    print("\n  Mock 合规检查...")
    # 检测 import 语句和函数调用（避免误匹配变量名如 mock_data）
    mock_import_pattern = re.compile(r"from unittest\.mock import|import unittest\.mock|from pytest_mock\b")
    mock_call_pattern = re.compile(r"Mock\s*\(|MagicMock\s*\(|patch\s*\(|mocker\.\w+")
    reason_pattern = re.compile(r"#\s*MOCK-REASON:")
    real_test_pattern = re.compile(r"#\s*MOCK-REAL-TEST:\s*(.+)")
    expire_pattern = re.compile(r"#\s*MOCK-EXPIRE-WHEN:")
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
        if not mock_import_pattern.search(content) and not mock_call_pattern.search(content):
            continue

        rel_path = str(py_file.relative_to(project_dir))

        # 检查 1：必须有 MOCK-REASON
        if not reason_pattern.search(content):
            violations.append(f"{rel_path}: 使用了 Mock 但缺少 # MOCK-REASON:")

        # 检查 2：必须有 MOCK-REAL-TEST 且路径有效
        real_test_match = real_test_pattern.search(content)
        if not real_test_match:
            violations.append(f"{rel_path}: 缺少 # MOCK-REAL-TEST: 声明")
        else:
            real_test_path = real_test_match.group(1).strip().split("::")[0]
            if not (project_dir / real_test_path).exists():
                violations.append(
                    f"{rel_path}: MOCK-REAL-TEST 指向 {real_test_path}，但该文件不存在"
                )

        # 检查 3：必须有 MOCK-EXPIRE-WHEN
        if not expire_pattern.search(content):
            violations.append(f"{rel_path}: 缺少 # MOCK-EXPIRE-WHEN: 声明")

    if violations:
        print(f"  FAIL  {len(violations)} 个 Mock 合规问题：")
        for v in violations[:10]:
            print(f"        {v}")
        if len(violations) > 10:
            print(f"        ... 还有 {len(violations) - 10} 个")
        _check_cache[cache_key] = False
        return False
    print("  PASS  Mock 使用合规（声明完整 + 真实测试存在）")
    _check_cache[cache_key] = True
    return True


def gate_7_final(project_dir: Path, **kwargs) -> bool:
    """Gate 7: 最终验收"""
    print("\n[Gate 7] 最终验收")

    # 运行与 Gate 5 相同的检查（直接调用公共函数，避免嵌套调用导致重复执行）
    if not _run_l1_regression(project_dir):
        return False
    if not _run_l2_integration(project_dir):
        return False
    if not check_mock_compliance(project_dir):
        return False
    if not _run_lint(project_dir):
        return False

    # 检查空实现（跨平台兼容：使用 os.walk 替代 rglob，提前剪枝排除目录）
    print("\n  空实现检查...")
    not_impl_found = []
    for root, dirs, files in os.walk(project_dir):
        # 提前剪枝：移除需要跳过的目录，避免遍历
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            py_file = Path(root) / fname
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

    # init-mode (iter-0) 时检查 feature-checklist.json
    state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            current_iteration = state.get("current_iteration", "")
        except Exception:
            current_iteration = ""
        if current_iteration == "iter-0":
            checklist_path = project_dir / ".claude" / "dev-state" / "feature-checklist.json"
            if checklist_path.exists():
                print("\n  Feature Checklist 检查（init-mode）...")
                try:
                    checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
                    not_pass = []
                    for feature in checklist if isinstance(checklist, list) else checklist.get("features", []):
                        fname = feature.get("name", feature.get("id", "unknown"))
                        fstatus = feature.get("status", "unknown")
                        if fstatus != "PASS":
                            not_pass.append(f"{fname}: {fstatus}")
                    if not_pass:
                        print(f"  FAIL  {len(not_pass)} 个 feature 未通过：")
                        for entry in not_pass:
                            print(f"        {entry}")
                        print(f"\n  Gate 7: FAIL")
                        return False
                    else:
                        print("  PASS  所有 feature 均为 PASS")
                except Exception as e:
                    print(f"  FAIL  feature-checklist.json 解析失败: {e}")
                    print(f"\n  Gate 7: FAIL")
                    return False

    print(f"\n  Gate 7: PASS")
    return True


def main() -> None:
    _check_cache.clear()
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
    if not project_dir.is_dir():
        print(f"ERROR: --project-dir 目录不存在: {project_dir}")
        sys.exit(1)

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
                results.append((name, "SKIP"))
                continue
            result = fn(project_dir, **extra)
            results.append((name, result))

        print(f"\n{'='*50}")
        print("门控汇总:")
        for name, result in results:
            if result == "SKIP":
                label = "SKIP"
            elif result:
                label = "PASS"
            else:
                label = "FAIL"
            print(f"  {label}  {name}")

        skipped = [name for name, r in results if r == "SKIP"]
        if skipped:
            print(f"\n  注意: 以下门控被 SKIP（非 PASS），请人工确认: {', '.join(skipped)}")

        if any(not r and r != "SKIP" for _, r in results):
            sys.exit(1)
    elif args.gate:
        passed = gates[args.gate](project_dir, **extra)
        if not passed:
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
