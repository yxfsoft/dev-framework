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
import py_compile
import subprocess
import sys
from pathlib import Path

# 添加 scripts 目录到 path 以导入 fw_utils
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import validate_safe_id


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
        print(f"  [FAIL]  {task_id}: verify 脚本不存在 ({verify_script})")
        print(f"        每个 CR 必须有独立的 verify 脚本，请 analyst 子代理先生成")
        return False  # 缺失 verify 脚本视为失败

    # 预检查: NotImplementedError 骨架占位
    try:
        script_content = verify_script.read_text(encoding="utf-8")
        ni_count = script_content.count("raise NotImplementedError")
        if ni_count > 0:
            print(f"  [ERROR] {task_id}: verify 脚本包含 {ni_count} 处 raise NotImplementedError，analyst 子代理必须先补全验证逻辑")
            return False
    except OSError as e:
        print(f"  [ERROR] {task_id}: 无法读取 verify 脚本: {e}")
        return False

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
        encoding="utf-8",
        errors="replace",
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
    """更新任务文件中的验收状态。

    将任务 YAML 的 status 字段更新为 ready_for_review（通过）或 rework（失败）。
    注意：逐条 acceptance_criteria 的状态更新由 verifier 子代理手动执行，
    此函数仅更新任务整体状态。
    """
    status_label = "PASS" if passed else "FAIL"
    print(f"\n  验收结果: {task_id} = {status_label}")

    task_path = (
        project_dir / ".claude" / "dev-state" / iteration_id / "tasks" / f"{task_id}.yaml"
    )
    if not task_path.exists():
        print(f"  [WARN]  任务文件不存在，跳过状态更新: {task_path}")
        return

    try:
        import yaml

        content = task_path.read_text(encoding="utf-8")
        task = yaml.safe_load(content)
        if not task:
            return

        new_status = "ready_for_review" if passed else "rework"
        task["status"] = new_status
        task_path.write_text(
            yaml.dump(task, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        print(f"  任务状态已更新: {task_id} → {new_status}")
    except ImportError:
        print(f"  [ERROR]  PyYAML 未安装，无法自动更新任务文件。运行: pip install PyYAML>=6.0")
        return
    except Exception as e:
        print(f"  [WARN]  更新任务文件失败: {e}")


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


def dry_run_verify(project_dir: Path, iteration_id: str, task_id: str | None) -> bool:
    """预验证 verify 脚本（不执行业务逻辑）。

    检查项：
    1. Python 语法正确（py_compile）
    2. 无 NotImplementedError 占位符
    3. 存在 main() 函数
    4. 包含 EVIDENCE_JSON 输出协议标记

    task_id=None 时检查全部。返回 True=全部通过。
    """
    verify_dir = project_dir / ".claude" / "dev-state" / iteration_id / "verify"
    if not verify_dir.exists():
        print(f"[FAIL] verify/ 目录不存在: {verify_dir}")
        return False

    if task_id and task_id != "__ALL__":
        scripts = [verify_dir / f"{task_id}.py"]
    else:
        scripts = sorted(verify_dir.glob("*.py"))

    if not scripts:
        print(f"[WARN] 无 verify 脚本可检查")
        return True

    all_passed = True
    for script_path in scripts:
        if not script_path.exists():
            print(f"  [FAIL] {script_path.name}: 文件不存在")
            all_passed = False
            continue

        tid = script_path.stem
        errors = []

        # Check 1: Python 语法
        try:
            py_compile.compile(str(script_path), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"语法错误: {e}")

        # Read content for remaining checks
        try:
            content = script_path.read_text(encoding="utf-8")
        except OSError as e:
            errors.append(f"无法读取: {e}")
            content = ""

        if content:
            # Check 2: NotImplementedError 占位符
            ni_count = content.count("raise NotImplementedError")
            if ni_count > 0:
                errors.append(f"包含 {ni_count} 处 raise NotImplementedError 占位符")

            # Check 3: main() 函数
            if "def main()" not in content:
                errors.append("缺少 main() 函数定义")

            # Check 4: EVIDENCE_JSON 输出协议标记
            if "EVIDENCE_JSON" not in content:
                errors.append("缺少 EVIDENCE_JSON 输出协议标记")

        if errors:
            print(f"  [FAIL] {tid}:")
            for err in errors:
                print(f"         - {err}")
            all_passed = False
        else:
            print(f"  [PASS] {tid}: dry-run 检查通过")

    return all_passed


def generate_skeleton(
    project_dir: Path, iteration_id: str, task_id: str
) -> None:
    """从任务 YAML 的 acceptance_criteria 自动生成 verify 脚本骨架。

    骨架包含每条 criteria 对应的 verify 函数（含 NotImplementedError 占位）
    和 done_evidence 自动收集逻辑。analyst 子代理必须检查并补全业务验证逻辑。

    参考模板：templates/verify/verify-task.py.tmpl
    """
    import yaml

    task_path = (
        project_dir
        / ".claude"
        / "dev-state"
        / iteration_id
        / "tasks"
        / f"{task_id}.yaml"
    )

    if not task_path.exists():
        print(f"错误: 任务文件不存在: {task_path}")
        sys.exit(1)

    task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    raw_ac = task.get("acceptance_criteria", [])
    title = task.get("title", "未知任务")

    # acceptance_criteria 仅支持 dict 格式（按维度分组）
    if isinstance(raw_ac, dict):
        criteria = []
        for group_name in ("functional", "robustness", "performance",
                           "ux_states", "ux_interaction", "security", "observability"):
            criteria.extend(raw_ac.get(group_name, []))
    else:
        criteria = []

    if not criteria:
        print(f"错误: {task_id} 无 acceptance_criteria")
        sys.exit(1)

    # 生成脚本
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    lines = [
        '#!/usr/bin/env python3',
        '"""',
        f'{task_id} 验收脚本',
        f'需求: {title}',
        f'生成时间: {now}',
        '',
        '此脚本骨架由 run-verify.py --generate-skeleton 自动生成。',
        'analyst 子代理必须补全每个 verify 函数的业务验证逻辑。',
        'developer 子代理和 verifier 子代理不可修改此脚本。',
        '零 Mock，使用真实环境验证。',
        '"""',
        '',
        'import json',
        'import sys',
        'import traceback',
        'from datetime import datetime, timezone',
        '',
    ]

    # 生成每个 criteria 的 verify 函数
    for i, ac in enumerate(criteria):
        ac_id = ac.get("id", f"{task_id}-AC{i+1}")
        ac_desc = ac.get("desc", f"验收标准 {i+1}")
        lines.extend([
            f'def verify_{ac_id.lower().replace("-", "_")}():',
            f'    """{ac_desc}"""',
            f'    # TODO: analyst 子代理必须补全此函数的验证逻辑',
            f'    raise NotImplementedError("analyst 子代理必须补全: {ac_desc}")',
            '',
        ])

    # 生成 collect_evidence 函数
    lines.extend([
        '',
        'def collect_evidence(results, task_id):',
        '    """收集 done_evidence（供 Verifier 使用）"""',
        '    timestamp = datetime.now(timezone.utc).isoformat()',
        '    passed = sum(1 for _, s, _, _ in results if s == "PASS")',
        '    total = len(results)',
        '    return {',
        '        "tests": [f"{task_id} verify: {passed}/{total} PASS ({timestamp})"],',
        '        "logs": [f"{ac_id}: {status} - {desc}" for ac_id, status, desc, _ in results],',
        '        "notes": ["全部通过" if passed == total else "存在失败项，需要修复"],',
        '    }',
        '',
    ])

    # 生成 main
    criteria_list = []
    for i, ac in enumerate(criteria):
        ac_id = ac.get("id", f"{task_id}-AC{i+1}")
        ac_desc = ac.get("desc", f"验收标准 {i+1}")
        func_name = f'verify_{ac_id.lower().replace("-", "_")}'
        criteria_list.append(f'        ("{ac_id}", "{ac_desc}", {func_name}),')

    lines.extend([
        '',
        'def main():',
        '    results = []',
        '    criteria = [',
    ])
    lines.extend(criteria_list)
    lines.extend([
        '    ]',
        '',
        '    for ac_id, desc, fn in criteria:',
        '        try:',
        '            fn()',
        '            results.append((ac_id, "PASS", desc, ""))',
        '            print(f"  [PASS]  {ac_id}: {desc}")',
        '        except AssertionError as e:',
        '            results.append((ac_id, "FAIL", desc, str(e)))',
        '            print(f"  [FAIL]  {ac_id}: {desc}")',
        '            print(f"        原因: {e}")',
        '        except NotImplementedError as e:',
        '            results.append((ac_id, "ERROR", desc, str(e)))',
        '            print(f"  [ERROR] {ac_id}: {desc}")',
        '            print(f"        未实现: {e}")',
        '        except Exception as e:',
        '            results.append((ac_id, "ERROR", desc, traceback.format_exc()))',
        '            print(f"  [ERROR] {ac_id}: {desc}")',
        '            print(f"        异常: {e}")',
        '',
        '    passed = sum(1 for _, s, _, _ in results if s == "PASS")',
        '    total = len(results)',
        '    print("\\n" + "=" * 50)',
        f'    print(f"{task_id} 验收结果: {{passed}}/{{total}} PASS")',
        '',
        '    # 输出 done_evidence JSON（供 Verifier 解析）',
        f'    evidence = collect_evidence(results, "{task_id}")',
        '    print(f"\\n--- EVIDENCE_JSON ---")',
        '    print(json.dumps(evidence, indent=2, ensure_ascii=False))',
        '    print(f"--- END_EVIDENCE ---")',
        '',
        '    if passed < total:',
        '        sys.exit(1)',
        '    else:',
        '        print("\\n全部通过!")',
        '        sys.exit(0)',
        '',
        '',
        'if __name__ == "__main__":',
        '    main()',
    ])

    verify_dir = (
        project_dir / ".claude" / "dev-state" / iteration_id / "verify"
    )
    verify_dir.mkdir(parents=True, exist_ok=True)
    verify_path = verify_dir / f"{task_id}.py"
    verify_path.write_text('\n'.join(lines), encoding="utf-8")

    print(f"骨架脚本已生成: {verify_path}")
    print(f"包含 {len(criteria)} 个验收函数 + done_evidence 收集逻辑")
    print(f"\n注意: analyst 子代理必须检查并补全每个 verify 函数的业务验证逻辑！")
    print(f"骨架中的 NotImplementedError 会导致运行时直接报错。")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行验收脚本")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument("--iteration-id", required=True, help="迭代 ID")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task-id", help="单个任务 ID")
    group.add_argument("--all", action="store_true", help="运行所有验收脚本")
    group.add_argument(
        "--generate-skeleton",
        metavar="TASK_ID",
        help="从任务 YAML 自动生成 verify 脚本骨架（analyst 子代理辅助）",
    )
    group.add_argument(
        "--dry-run",
        nargs="?",
        const="__ALL__",
        metavar="TASK_ID",
        help="预验证 verify 脚本（不执行业务逻辑）。省略 TASK_ID 时检查全部",
    )

    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        sys.exit(f"ERROR: --project-dir 目录不存在: {project_dir}")

    # SEC01: 路径遍历检测
    validate_safe_id(args.iteration_id, "iteration-id")
    _task_id = args.task_id or args.generate_skeleton
    if _task_id:
        validate_safe_id(_task_id, "task-id")
    if args.dry_run and args.dry_run != "__ALL__":
        validate_safe_id(args.dry_run, "task-id")

    if args.dry_run is not None:
        tid = args.dry_run if args.dry_run != "__ALL__" else None
        passed = dry_run_verify(project_dir, args.iteration_id, tid)
        if not passed:
            sys.exit(1)
    elif args.generate_skeleton:
        generate_skeleton(project_dir, args.iteration_id, args.generate_skeleton)
    elif args.all:
        run_all_verify(project_dir, args.iteration_id)
    else:
        passed = run_single_verify(project_dir, args.iteration_id, args.task_id)
        if not passed:
            sys.exit(1)


if __name__ == "__main__":
    main()
