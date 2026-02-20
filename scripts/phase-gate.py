#!/usr/bin/env python3
"""
phase-gate.py — Phase 转换门控检查（FIX-02）

在 Phase N → Phase N+1 转换时运行，检查前置条件是否满足。
返回码 0 = 通过，非 0 = 阻断。

用法:
    python dev-framework/scripts/phase-gate.py \
        --project-dir "D:/project" \
        --iteration-id "iter-1" \
        --from phase_2 --to phase_3

    # 强制跳过（需记录到 decisions.md）
    python dev-framework/scripts/phase-gate.py \
        --project-dir "D:/project" \
        --iteration-id "iter-1" \
        --from phase_2 --to phase_3 \
        --force
"""

from __future__ import annotations  # 支持 Python 3.7+ 新式类型注解

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def check_phase_2_to_3(iter_dir: Path) -> list[str]:
    """Phase 2→3（拆分→开发）的前置条件检查。"""
    errors = []
    tasks_dir = iter_dir / "tasks"
    verify_dir = iter_dir / "verify"

    # 检查 1：tasks 目录非空
    task_files = list(tasks_dir.glob("*.yaml")) if tasks_dir.exists() else []
    if not task_files:
        errors.append("tasks/ 目录为空，Analyst 尚未完成任务拆分")

    # 检查 2：每个 task 必须有对应的 verify 脚本
    for tf in task_files:
        task_id = tf.stem
        verify_file = verify_dir / f"{task_id}.py"
        if not verify_file.exists():
            errors.append(f"缺少 verify 脚本: verify/{task_id}.py")

    # 检查 3：verify 脚本质量底线（FIX-03: 至少不能全是字符串搜索）
    if verify_dir.exists():
        for vf in verify_dir.glob("*.py"):
            try:
                content = vf.read_text(encoding="utf-8")
            except OSError:
                errors.append(f"verify/{vf.name}: 无法读取文件")
                continue

            # M33: 更精确的运行时断言检查（跳过注释行）
            runtime_keywords = [
                "subprocess.run", "import requests", "assert ",
                "pytest.mark", "pytest.raises", "unittest",
                ".json()", "response.status_code",
                "importlib", "raise AssertionError",
            ]
            has_runtime_assertion = any(
                kw in line
                for line in content.splitlines()
                if not line.strip().startswith("#")
                for kw in runtime_keywords
            )
            # 检测是否仅包含字符串存在性检查
            has_only_string_check = (
                ('" in source' in content or "' in source" in content)
                or ('" in content' in content or "' in content" in content)
            )
            if has_only_string_check and not has_runtime_assertion:
                errors.append(
                    f"verify/{vf.name}: 仅包含字符串存在性检查，"
                    "缺少运行时断言（至少需要 1 个 subprocess.run/assert/pytest 调用）"
                )

    # 检查 4：manifest phase 应为 phase_2
    manifest = iter_dir / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("phase") != "phase_2":
            errors.append(f"manifest.json phase={data.get('phase')}，预期 phase_2")

    return errors


def check_phase_3_to_3_5(iter_dir: Path) -> list[str]:
    """Phase 3→3.5（开发→验收）的前置条件检查。"""
    errors = []
    tasks_dir = iter_dir / "tasks"

    if yaml is None:
        errors.append("PyYAML 未安装，无法解析任务文件")
        return errors

    if not tasks_dir.exists():
        errors.append("tasks/ 目录不存在")
        return errors

    for tf in tasks_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(tf.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{tf.name}: YAML 解析失败 — {e}")
            continue
        if not data:
            continue
        status = data.get("status", "pending")
        if status not in ("ready_for_verify", "ready_for_review", "PASS"):
            errors.append(f"{tf.name}: status={status}，预期 ready_for_verify 或更后的状态")

    return errors


def check_phase_3_5_to_4(iter_dir: Path) -> list[str]:
    """Phase 3.5→4（验收→审查）的前置条件检查。"""
    errors = []
    tasks_dir = iter_dir / "tasks"
    if yaml is None:
        errors.append("PyYAML 未安装，无法解析任务文件")
        return errors
    if not tasks_dir.exists():
        errors.append("tasks/ 目录不存在")
        return errors
    for tf in tasks_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(tf.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{tf.name}: YAML 解析失败 — {e}")
            continue
        if not data:
            continue
        status = data.get("status", "pending")
        if status not in ("ready_for_review", "PASS"):
            errors.append(f"{tf.name}: status={status}，预期 ready_for_review 或 PASS")
    return errors


def check_phase_4_to_5(iter_dir: Path) -> list[str]:
    """Phase 4→5（审查→完成）的前置条件检查。"""
    errors = []
    tasks_dir = iter_dir / "tasks"

    if yaml is None:
        errors.append("PyYAML 未安装，无法解析任务文件")
        return errors

    if not tasks_dir.exists():
        errors.append("tasks/ 目录不存在")
        return errors

    for tf in tasks_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(tf.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{tf.name}: YAML 解析失败 — {e}")
            continue
        if not data:
            continue
        task_id = data.get("id", tf.stem)

        # 检查 1：status 必须为 PASS
        status = data.get("status", "pending")
        if status != "PASS":
            errors.append(f"{task_id}: status={status}，预期 PASS")

        # 检查 2：done_evidence 不得为空
        evidence = data.get("done_evidence")
        if not evidence or (isinstance(evidence, dict) and not evidence.get("tests")):
            errors.append(f"{task_id}: done_evidence 为空或缺少 tests 字段")

        # 检查 3：review_result 不得为空
        review = data.get("review_result")
        if not review or (isinstance(review, dict) and not review.get("verdict")):
            errors.append(f"{task_id}: review_result 为空或缺少 verdict 字段")

    # 检查 4：verify 目录不得为空
    verify_dir = iter_dir / "verify"
    if not verify_dir.exists() or not list(verify_dir.glob("*.py")):
        errors.append("verify/ 目录为空")

    return errors


def _update_manifest_phase(iter_dir: Path, new_phase: str) -> None:
    """更新 manifest.json 中的 phase 字段。"""
    manifest = iter_dir / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["phase"] = new_phase
        manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


GATE_MAP = {
    ("phase_2", "phase_3"): check_phase_2_to_3,
    ("phase_3", "phase_3.5"): check_phase_3_to_3_5,
    ("phase_3.5", "phase_4"): check_phase_3_5_to_4,   # 专用函数：检查验收完成
    ("phase_4", "phase_5"): check_phase_4_to_5,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 转换门控检查")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument("--iteration-id", required=True, help="迭代 ID")
    parser.add_argument("--from", dest="from_phase", required=True, help="当前 Phase")
    parser.add_argument("--to", dest="to_phase", required=True, help="目标 Phase")
    parser.add_argument(
        "--force", action="store_true",
        help="强制跳过门控（必须在 decisions.md 中记录原因）"
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: --project-dir 目录不存在: {project_dir}")
        return 1
    iter_dir = project_dir / ".claude" / "dev-state" / args.iteration_id
    key = (args.from_phase, args.to_phase)
    checker = GATE_MAP.get(key)

    if not checker:
        # M34: 明确输出放行信息
        print(f"[PASS] {key[0]}→{key[1]}: 自动放行（无前置门控检查）")
        return 0

    errors = checker(iter_dir)

    if errors and args.force:
        print(f"[FORCE] {key[0]}→{key[1]} 门控有 {len(errors)} 个问题，但使用了 --force 跳过：")
        for e in errors:
            print(f"  - {e}")
        print("\n[WARN] 必须在 decisions.md 中记录跳过门控的原因！")
        _update_manifest_phase(iter_dir, args.to_phase)
        return 0

    if errors:
        print(f"[BLOCKED] {key[0]}→{key[1]} 转换被阻断（{len(errors)} 个问题）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print(f"[PASS] {key[0]}→{key[1]} 门控通过")
        _update_manifest_phase(iter_dir, args.to_phase)
        return 0


if __name__ == "__main__":
    sys.exit(main())
