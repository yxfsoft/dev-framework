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
from datetime import datetime, timezone
from pathlib import Path

import yaml


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
                print(f"  WARN: 解析 {f} 失败: {e}", file=__import__('sys').stderr)

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
    """生成恢复上下文摘要"""
    dev_state = project_dir / ".claude" / "dev-state"
    state_path = dev_state / "session-state.json"

    if not state_path.exists():
        print("无 session 状态。这是一个全新的 session。")
        return

    state = json.loads(state_path.read_text())
    iteration_id = state.get("current_iteration", "unknown")

    # 读取最新检查点
    cp_dir = dev_state / iteration_id / "checkpoints"
    last_cp = ""
    if cp_dir.exists():
        cps = sorted(cp_dir.glob("cp-*.md"))
        if cps:
            last_cp = cps[-1].read_text(encoding="utf-8")

    # 读取 decisions
    decisions_path = dev_state / iteration_id / "decisions.md"
    decisions = ""
    if decisions_path.exists():
        decisions = decisions_path.read_text(encoding="utf-8")

    # 输出摘要
    progress = state.get("progress", {})
    print("=" * 50)
    print("Session 恢复摘要")
    print("=" * 50)
    print(f"\n迭代: {iteration_id}")
    print(f"阶段: {state.get('current_phase', '?')}")
    print(f"进度: {progress.get('completed', 0)}/{progress.get('total_tasks', 0)} CR 完成")
    print(f"当前任务: {state.get('current_task', '无')}")
    print(f"上次更新: {state.get('last_updated', '?')}")

    if last_cp:
        print(f"\n最新检查点:\n{last_cp[:500]}")

    if decisions and len(decisions) > 50:
        print(f"\n关键决策:\n{decisions[-300:]}")

    print(f"\n建议: 读取上述信息后继续工作。")


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
                print(f"  WARN: 解析 {f} 失败: {e}", file=__import__('sys').stderr)

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
