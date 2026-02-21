#!/usr/bin/env python3
"""
phase-gate.py — Phase 转换门控检查

在 Phase N → Phase N+1 转换时运行，检查前置条件是否满足。
返回码 0 = 通过，非 0 = 阻断。

用法:
    python dev-framework/scripts/phase-gate.py \
        --project-dir "<项目路径>" \
        --iteration-id "iter-1" \
        --from phase_2 --to phase_3

    # 强制跳过（需记录到 decisions.md）
    python dev-framework/scripts/phase-gate.py \
        --project-dir "<项目路径>" \
        --iteration-id "iter-1" \
        --from phase_2 --to phase_3 \
        --force
"""

from __future__ import annotations  # 支持 Python 3.7+ 新式类型注解

import argparse
import json
import sys
from pathlib import Path

# 添加 scripts 目录到 path 以导入 fw_utils
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import validate_manifest, PHASE_NUMS

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def check_phase_0_to_1(iter_dir: Path) -> list[str]:
    """Phase 0→1: 检查环境就绪。"""
    errors = []
    manifest = iter_dir / "manifest.json"
    if not manifest.exists():
        errors.append("manifest.json 不存在，请先运行 init-iteration.py")
    return errors


def check_phase_1_to_2(iter_dir: Path) -> list[str]:
    """Phase 1→2: 检查需求规格书存在。"""
    errors = []
    req_spec = iter_dir / "requirement-spec.md"
    if not req_spec.exists():
        errors.append("requirement-spec.md 不存在，需求深化尚未完成")
    return errors


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
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"manifest.json 读取/解析失败: {e}")
            return errors
        # C2: 加载后校验 manifest 完整性（仅 WARN，不阻断）
        m_errors = validate_manifest(data)
        if m_errors:
            for e in m_errors:
                print(f"  [WARN] manifest 校验: {e}")
        if data.get("phase") != "phase_2":
            errors.append(
                f"manifest.json phase={data.get('phase')}，预期 phase_2。"
                "请确保已执行 phase-gate.py --from phase_1 --to phase_2"
            )

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
        # hotfix 类型走快速通道，跳过状态检查
        task_type = data.get("type", "")
        if task_type == "hotfix":
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
        # hotfix 类型走快速通道，跳过状态检查
        task_type = data.get("type", "")
        if task_type == "hotfix":
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
        # hotfix 类型走快速通道，仅检查 status==PASS
        task_type = data.get("type", "")
        if task_type == "hotfix":
            if data.get("status", "pending") != "PASS":
                errors.append(f"{task_id}: hotfix status={data.get('status')}，预期 PASS")
            # hotfix 仍需 L1 基线回归通过
            evidence = data.get("done_evidence")
            if not evidence or (isinstance(evidence, dict) and not any(
                evidence.get(field) for field in ("tests", "logs", "notes")
            )):
                errors.append(f"{task_id}: hotfix done_evidence 为空（需记录 L1 基线回归结果）")
            continue

        # 检查 1：status 必须为 PASS
        status = data.get("status", "pending")
        if status != "PASS":
            errors.append(f"{task_id}: status={status}，预期 PASS")

        # 检查 2：done_evidence 不得为空（tests/logs/notes 任一非空即可）
        evidence = data.get("done_evidence")
        if not evidence or (isinstance(evidence, dict) and not any(
            evidence.get(field) for field in ("tests", "logs", "notes")
        )):
            errors.append(f"{task_id}: done_evidence 为空（tests/logs/notes 至少一项需非空）")

        # 检查 3：review_result 不得为空
        review = data.get("review_result")
        if not review or (isinstance(review, dict) and not review.get("verdict")):
            errors.append(f"{task_id}: review_result 为空或缺少 verdict 字段")

    # 检查 4：verify 目录不得为空
    verify_dir = iter_dir / "verify"
    if not verify_dir.exists() or not list(verify_dir.glob("*.py")):
        errors.append("verify/ 目录为空")

    return errors


def check_phase_5_complete(iter_dir: Path) -> list[str]:
    """Phase 5 完成检查：验证迭代是否满足所有交付条件。"""
    errors = []

    if yaml is None:
        errors.append("PyYAML 未安装，无法解析任务文件")
        return errors

    tasks_dir = iter_dir / "tasks"
    if not tasks_dir.exists():
        errors.append("tasks/ 目录不存在")
        return errors

    # 检查 1：所有 CR status=PASS
    task_files = list(tasks_dir.glob("*.yaml"))
    if not task_files:
        errors.append("tasks/ 目录为空")
    for tf in task_files:
        try:
            data = yaml.safe_load(tf.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            errors.append(f"{tf.name}: 读取/解析失败 — {e}")
            continue
        if not data:
            continue
        task_id = data.get("id", tf.stem)
        status = data.get("status", "pending")
        if status != "PASS":
            errors.append(f"{task_id}: status={status}，预期 PASS")

    # 检查 2：所有非 hotfix CR 的 review_result.verdict=PASS
    for tf in task_files:
        try:
            data = yaml.safe_load(tf.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            continue
        if not data:
            continue
        task_id = data.get("id", tf.stem)
        task_type = data.get("type", "")
        if task_type == "hotfix":
            continue
        review = data.get("review_result")
        if not review or review.get("verdict") != "PASS":
            errors.append(f"{task_id}: review_result.verdict 不为 PASS")

    # 检查 3：checkpoints/ 非空
    cp_dir = iter_dir / "checkpoints"
    if not cp_dir.exists() or not list(cp_dir.glob("cp-*.md")):
        errors.append("checkpoints/ 目录为空，缺少进度快照")

    # 检查 4：verify/ 非空
    verify_dir = iter_dir / "verify"
    if not verify_dir.exists() or not list(verify_dir.glob("*.py")):
        errors.append("verify/ 目录为空，缺少验收脚本")

    return errors


def _update_manifest_phase(iter_dir: Path, new_phase: str) -> None:
    """更新 manifest.json 中的 phase 字段，并同步更新 session-state.json。"""
    manifest = iter_dir / "manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [ERROR] manifest.json 读取/解析失败: {e}")
            return
        # C2: 加载后校验 manifest 完整性（仅 WARN，不阻断）
        m_errors = validate_manifest(data)
        if m_errors:
            for e in m_errors:
                print(f"  [WARN] manifest 校验: {e}")
        data["phase"] = new_phase
        manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # 同步更新 session-state.json 的 current_phase
    try:
        session_state = iter_dir.parent / "session-state.json"
        if session_state.exists():
            state = json.loads(session_state.read_text(encoding="utf-8"))
            state["current_phase"] = new_phase
            session_state.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except (json.JSONDecodeError, OSError):
        pass  # 非关键路径，静默跳过


GATE_MAP = {
    ("phase_0", "phase_1"): check_phase_0_to_1,
    ("phase_1", "phase_2"): check_phase_1_to_2,
    ("phase_2", "phase_3"): check_phase_2_to_3,
    ("phase_3", "phase_3.5"): check_phase_3_to_3_5,
    ("phase_3.5", "phase_4"): check_phase_3_5_to_4,
    ("phase_4", "phase_5"): check_phase_4_to_5,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 转换门控检查")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument("--iteration-id", required=True, help="迭代 ID")
    parser.add_argument("--from", dest="from_phase", required=False, help="当前 Phase")
    parser.add_argument("--to", dest="to_phase", required=False, help="目标 Phase")
    parser.add_argument(
        "--force", action="store_true",
        help="强制跳过门控（必须在 decisions.md 中记录原因）"
    )
    parser.add_argument(
        "--check-completion", action="store_true",
        help="检查 Phase 5 是否满足所有交付条件（独立于 Phase 转换使用）"
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: --project-dir 目录不存在: {project_dir}")
        return 1
    iter_dir = project_dir / ".claude" / "dev-state" / args.iteration_id

    # --check-completion: 独立检查 Phase 5 交付条件
    if args.check_completion:
        errors = check_phase_5_complete(iter_dir)
        if errors:
            print(f"[BLOCKED] Phase 5 完成检查未通过（{len(errors)} 个问题）：")
            for e in errors:
                print(f"  - {e}")
            return 1
        else:
            print("[PASS] Phase 5 完成检查通过：所有 CR 为 PASS，review 通过，checkpoints 和 verify 非空")
            return 0

    if not args.from_phase or not args.to_phase:
        print("ERROR: Phase 转换模式需要 --from 和 --to 参数")
        return 1

    key = (args.from_phase, args.to_phase)
    checker = GATE_MAP.get(key)

    if not checker:
        # 解析 phase 数值用于判断方向
        def _phase_num(p: str) -> float:
            if not p.startswith("phase_"):
                print(f"[ERROR] 无效的 Phase 格式: '{p}'，预期格式: phase_N 或 phase_N.5（如 phase_0, phase_3.5）")
                return -1.0
            s = p.replace("phase_", "")
            if not s:
                print(f"[ERROR] 无效的 Phase 格式: '{p}'，缺少阶段编号。预期格式: phase_N 或 phase_N.5")
                return -1.0
            try:
                num = float(s)
                if num not in PHASE_NUMS:
                    print(f"[ERROR] 无效的 Phase 编号: '{p}'，合法值: {', '.join(f'phase_{v}' for v in PHASE_NUMS)}")
                    return -1.0
                return num
            except ValueError:
                print(f"[ERROR] 无效的 Phase 格式: '{p}'，'{s}' 不是有效数字。预期格式: phase_N 或 phase_N.5")
                return -1.0

        from_num = _phase_num(args.from_phase)
        to_num = _phase_num(args.to_phase)

        if from_num < 0 or to_num < 0:
            return 1

        if to_num < from_num:
            # 回退操作：允许通过
            print(f"[PASS] {key[0]}→{key[1]}: 回退操作，自动放行")
            print(f"[WARN] 建议在 decisions.md 中记录回退原因")
            _update_manifest_phase(iter_dir, args.to_phase)
            return 0
        else:
            # 前进但无门控：检查是否为跳级（不允许跳过中间 Phase）
            if from_num in PHASE_NUMS and to_num in PHASE_NUMS:
                from_idx = PHASE_NUMS.index(from_num)
                to_idx = PHASE_NUMS.index(to_num)
                if to_idx - from_idx > 1:
                    print(f"[BLOCKED] {key[0]}→{key[1]}: Phase 转换必须顺序执行，"
                          f"不可跳过中间阶段。请先转换到 phase_{PHASE_NUMS[from_idx + 1]}")
                    return 1
            print(f"[WARN] {key[0]}→{key[1]}: 未找到对应门控检查，放行")
            _update_manifest_phase(iter_dir, args.to_phase)
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
