#!/usr/bin/env python3
"""
session-manager.py — Session 状态管理工具

用法:
    # 查看当前状态
    python dev-framework/scripts/session-manager.py \
        --project-dir "D:/project" status

    # 写入检查点
    python dev-framework/scripts/session-manager.py \
        --project-dir "D:/project" checkpoint

    # 恢复上下文摘要
    python dev-framework/scripts/session-manager.py \
        --project-dir "D:/project" resume
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML 未安装。运行: pip install PyYAML>=6.0")
    sys.exit(1)


# Phase 状态机
PHASE_ORDER = [
    "phase_0", "phase_1", "phase_2",
    "phase_3", "phase_3.5", "phase_4", "phase_5",
]


def validate_phase_transition(current: str, target: str) -> tuple[bool, str]:
    """校验 Phase 转换是否合法。返回 (合法, 原因)。"""
    if current not in PHASE_ORDER or target not in PHASE_ORDER:
        return False, f"未知 Phase: {current} → {target}"
    curr_idx = PHASE_ORDER.index(current)
    target_idx = PHASE_ORDER.index(target)
    # 正常前进（+1）
    if target_idx == curr_idx + 1:
        return True, "正常前进"
    # rework 回退到 phase_3
    if target == "phase_3" and current in ("phase_3.5", "phase_4"):
        return True, "rework 回退"
    # 同 phase（重新进入）
    if target_idx == curr_idx:
        return True, "同阶段重入"
    return False, f"非法跳转: {current} → {target}（跳过了中间阶段）"


def cmd_status(project_dir: Path) -> None:
    """查看当前状态"""
    dev_state = project_dir / ".claude" / "dev-state"
    state_path = dev_state / "session-state.json"

    if not state_path.exists():
        print("无 session 状态文件。请先运行 init-project.py 或 init-iteration.py。")
        return

    state = json.loads(state_path.read_text())

    print(f"Session: {state.get('session_id', '?')}")
    print(f"迭代: {state.get('current_iteration', '?')}")
    print(f"阶段: {state.get('current_phase', '?')}")
    print(f"当前任务: {state.get('current_task', '无')}")
    print(f"上次更新: {state.get('last_updated', '?')}")

    progress = state.get("progress", {})
    total = progress.get("total_tasks", 0)
    completed = progress.get("completed", 0)
    in_progress = progress.get("in_progress", 0)
    pending = progress.get("pending", 0)
    rework = progress.get("rework", 0)

    print(f"\n进度: {completed}/{total} 完成")
    print(f"  进行中: {in_progress}")
    print(f"  待做: {pending}")
    print(f"  返工: {rework}")

    # 输出当前 Phase 的合法下一步
    current_phase = state.get("current_phase", "")
    if current_phase and current_phase in PHASE_ORDER:
        valid_next = []
        for candidate in PHASE_ORDER:
            ok, reason = validate_phase_transition(current_phase, candidate)
            if ok and candidate != current_phase:
                valid_next.append(f"{candidate} ({reason})")
        if valid_next:
            print(f"\n合法的下一步 Phase:")
            for v in valid_next:
                print(f"  → {v}")


def cmd_checkpoint(project_dir: Path) -> None:
    """写入检查点"""
    dev_state = project_dir / ".claude" / "dev-state"
    state_path = dev_state / "session-state.json"

    if not state_path.exists():
        print("无 session 状态文件")
        return

    state = json.loads(state_path.read_text())
    iteration_id = state.get("current_iteration", "unknown")
    cp_dir = dev_state / iteration_id / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)

    # 找到下一个检查点编号
    existing = sorted(cp_dir.glob("cp-*.md"))
    next_num = len(existing) + 1
    cp_name = f"cp-{next_num:03d}"

    # 加载任务
    tasks_dir = dev_state / iteration_id / "tasks"
    tasks = []
    if tasks_dir.exists():
        for f in sorted(tasks_dir.glob("*.yaml")):
            try:
                task = yaml.safe_load(f.read_text(encoding="utf-8"))
                if task:
                    tasks.append(task)
            except Exception as e:
                print(f"  WARN: 解析 {f} 失败: {e}", file=sys.stderr)

    # 生成检查点
    now = datetime.now(timezone.utc).isoformat()
    completed_tasks = [t for t in tasks if t.get("status") == "PASS"]
    in_progress_tasks = [t for t in tasks if t.get("status") == "in_progress"]
    pending_tasks = [t for t in tasks if t.get("status") == "pending"]

    cp_content = f"""# Checkpoint {cp_name} — {now}

## 当前状态
- 迭代: {iteration_id}
- 阶段: {state.get('current_phase', '?')}
- 进度: {len(completed_tasks)}/{len(tasks)} CR 完成

## 已完成
"""
    for t in completed_tasks:
        cp_content += f"- {t['id']}: {t.get('title', '?')} (PASS)\n"

    cp_content += "\n## 进行中\n"
    for t in in_progress_tasks:
        cp_content += f"- {t['id']}: {t.get('title', '?')} ({t.get('owner', '?')})\n"

    cp_content += "\n## 待开始\n"
    for t in pending_tasks:
        cp_content += f"- {t['id']}: {t.get('title', '?')}\n"

    cp_content += f"\n## 下一步\n- (由 Leader 填写)\n"

    cp_path = cp_dir / f"{cp_name}.md"
    cp_path.write_text(cp_content, encoding="utf-8")

    # 更新 session-state
    state["last_checkpoint"] = f"{cp_name}.md"
    state["last_updated"] = now
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    print(f"检查点已写入: {cp_path}")


def cmd_resume(project_dir: Path) -> None:
    """生成恢复上下文摘要（完整版）

    扫描 session-state + 任务状态 + 检查点 + 决策 + 经验日志，
    输出完整恢复摘要并写入 resume-summary.md 文件供 Agent 随时重读。
    """
    dev_state = project_dir / ".claude" / "dev-state"
    state_path = dev_state / "session-state.json"

    if not state_path.exists():
        print("无 session 状态。这是一个全新的 session。")
        return

    state = json.loads(state_path.read_text())
    iteration_id = state.get("current_iteration", "unknown")
    iter_dir = dev_state / iteration_id
    lines: list[str] = []

    def emit(text: str = "") -> None:
        lines.append(text)
        print(text)

    emit("=" * 50)
    emit("Session 恢复摘要")
    emit("=" * 50)

    # 1. 基本状态
    progress = state.get("progress", {})
    emit(f"\n迭代: {iteration_id}")
    emit(f"阶段: {state.get('current_phase', '?')}")
    emit(f"进度: {progress.get('completed', 0)}/{progress.get('total_tasks', 0)} CR 完成")
    emit(f"当前任务: {state.get('current_task', '无')}")
    emit(f"上次更新: {state.get('last_updated', '?')}")

    # 2. 扫描任务状态
    tasks_dir = iter_dir / "tasks"
    if tasks_dir.exists():
        task_files = sorted(tasks_dir.glob("*.yaml"))
        if task_files:
            emit(f"\n{'─' * 40}")
            emit(f"任务状态 ({len(task_files)} 个):")
            for tf in task_files:
                try:
                    task = yaml.safe_load(tf.read_text(encoding="utf-8"))
                    if task:
                        tid = task.get("id", tf.stem)
                        status = task.get("status", "?")
                        title = task.get("title", "")[:50]
                        emit(f"  {status:20s} {tid}: {title}")
                except Exception:
                    emit(f"  {'ERROR':20s} {tf.stem}: (解析失败)")

    # 3. 最新检查点（完整内容）
    cp_dir = iter_dir / "checkpoints"
    if cp_dir.exists():
        cps = sorted(cp_dir.glob("cp-*.md"))
        if cps:
            last_cp = cps[-1].read_text(encoding="utf-8")
            emit(f"\n{'─' * 40}")
            emit(f"最新检查点 ({cps[-1].name}):")
            emit(last_cp)

    # 4. 关键决策（完整内容）
    decisions_path = iter_dir / "decisions.md"
    if decisions_path.exists():
        decisions = decisions_path.read_text(encoding="utf-8")
        if decisions.strip() and len(decisions) > 50:
            emit(f"\n{'─' * 40}")
            emit("关键决策:")
            emit(decisions)

    # 5. 经验日志摘要
    exp_path = dev_state / "experience-log.md"
    if exp_path.exists():
        exp_content = exp_path.read_text(encoding="utf-8")
        if exp_content.strip() and len(exp_content) > 50:
            emit(f"\n{'─' * 40}")
            emit("经验日志:")
            emit(exp_content)

    # 6. Git 最近提交
    try:
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if git_log.returncode == 0 and git_log.stdout.strip():
            emit(f"\n{'─' * 40}")
            emit("最近 Git 提交:")
            emit(git_log.stdout.strip())
    except Exception:
        emit("  (git log 获取失败)")

    # 7. 基线测试摘要
    baseline_path = dev_state / "baseline.json"
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text())
            test_results = baseline.get("test_results", {})
            emit(f"\n{'─' * 40}")
            emit("基线状态:")
            emit(f"  L1 passed: {test_results.get('l1_passed', '?')}")
            emit(f"  L2 passed: {test_results.get('l2_passed', '?')}")
            emit(f"  Lint clean: {baseline.get('lint_clean', '?')}")
        except Exception:
            emit("  (baseline.json 解析失败)")

    emit(f"\n{'=' * 50}")
    emit("建议: 读取上述信息后继续工作。")

    # 写入 resume-summary.md 供 Agent 随时重读
    summary_path = iter_dir / "resume-summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n恢复摘要已写入: {summary_path}")


def cmd_ledger(project_dir: Path) -> None:
    """写入 Session Ledger 记录（Team 并行子任务台账）"""
    dev_state = project_dir / ".claude" / "dev-state"
    state_path = dev_state / "session-state.json"

    if not state_path.exists():
        print("无 session 状态文件")
        return

    state = json.loads(state_path.read_text())
    iteration_id = state.get("current_iteration", "unknown")
    ledger_dir = dev_state / iteration_id / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    # 确定编号
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    existing = sorted(ledger_dir.glob(f"session-{date_str}-*.md"))
    seq = len(existing) + 1

    # 加载任务
    tasks_dir = dev_state / iteration_id / "tasks"
    tasks = []
    if tasks_dir.exists():
        for f in sorted(tasks_dir.glob("*.yaml")):
            try:
                task = yaml.safe_load(f.read_text(encoding="utf-8"))
                if task:
                    tasks.append(task)
            except Exception as e:
                print(f"  WARN: 解析 {f} 失败: {e}", file=sys.stderr)

    # 生成 ledger 内容
    content = f"# Session Ledger — {date_str}-{seq:02d}\n\n"
    content += f"## 基本信息\n"
    content += f"- iteration: {iteration_id}\n"
    content += f"- phase: {state.get('current_phase', '?')}\n"
    content += f"- timestamp: {now.isoformat()}\n\n"
    content += f"## Team 子任务\n\n"
    content += f"| Agent | CR | Status | Output |\n"
    content += f"|-------|-----|--------|--------|\n"

    for t in tasks:
        status = t.get("status", "?")
        if status in ("in_progress", "ready_for_verify", "ready_for_review", "PASS", "rework"):
            owner = t.get("owner", "-")
            tid = t.get("id", "?")
            title = t.get("title", "?")[:40]
            content += f"| {owner} | {tid} | {status} | {title} |\n"

    content += f"\n## 决策记录\n- (由 Leader 填写)\n"
    content += f"\n## 下一步行动\n- (由 Leader 填写)\n"

    ledger_path = ledger_dir / f"session-{date_str}-{seq:02d}.md"
    ledger_path.write_text(content, encoding="utf-8")

    # 更新 session-state
    state["last_updated"] = now.isoformat()
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    print(f"Session Ledger 已写入: {ledger_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Session 状态管理")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument(
        "command",
        choices=["status", "checkpoint", "resume", "ledger"],
        help="操作: status(查看状态), checkpoint(写入检查点), resume(恢复摘要), ledger(写入并行台账)",
    )
    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    commands = {
        "status": cmd_status,
        "checkpoint": cmd_checkpoint,
        "resume": cmd_resume,
        "ledger": cmd_ledger,
    }
    commands[args.command](project_dir)


if __name__ == "__main__":
    main()
