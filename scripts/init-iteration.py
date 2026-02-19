#!/usr/bin/env python3
"""
init-iteration.py — 在已有项目中初始化新一轮迭代

用法:
    python dev-framework/scripts/init-iteration.py \
        --project-dir "D:/existing-project" \
        --requirement "修复搜索超时；新增批量导入" \
        --iteration-id "iter-3"

执行后在项目中新增:
    .claude/dev-state/iteration-{id}/
        ├── manifest.json
        ├── requirement-raw.md
        ├── tasks/
        ├── verify/
        ├── checkpoints/
        └── decisions.md
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def init_iteration(
    project_dir: Path, requirement: str, iteration_id: str
) -> None:
    """初始化新一轮迭代"""
    project_dir = project_dir.resolve()
    dev_state = project_dir / ".claude" / "dev-state"

    if not dev_state.exists():
        print(f"错误: {dev_state} 不存在。请先运行 init-project.py 初始化项目。")
        return

    iter_dir = dev_state / iteration_id

    if iter_dir.exists():
        print(f"错误: {iter_dir} 已存在。请使用不同的 iteration-id。")
        return

    print(f"初始化迭代: {iteration_id}")
    print(f"项目: {project_dir}")
    print(f"需求: {requirement[:100]}...")
    print()

    # 1. 创建迭代目录结构
    subdirs = ["tasks", "verify", "checkpoints"]
    for d in subdirs:
        (iter_dir / d).mkdir(parents=True, exist_ok=True)
        print(f"  创建: {iteration_id}/{d}/")

    # 2. 生成 manifest.json
    manifest = {
        "id": iteration_id,
        "mode": "iterate",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requirement_summary": requirement[:200],
        "phase": "phase_0",
        "last_checkpoint": "",
    }
    manifest_path = iter_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"  生成: manifest.json")

    # 3. 写入原始需求
    raw_req_path = iter_dir / "requirement-raw.md"
    raw_req_path.write_text(
        f"# 原始需求 — {iteration_id}\n\n"
        f"提交时间: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"## 需求内容\n\n{requirement}\n",
        encoding="utf-8",
    )
    print(f"  生成: requirement-raw.md")

    # 4. 生成空 decisions.md
    decisions_path = iter_dir / "decisions.md"
    decisions_path.write_text(
        f"# 关键决策日志 — {iteration_id}\n\n"
        f"> 记录本轮迭代中的关键技术决策。\n\n---\n",
        encoding="utf-8",
    )
    print(f"  生成: decisions.md")

    # 5. 更新 session-state.json
    session_state_path = dev_state / "session-state.json"
    if session_state_path.exists():
        session_state = json.loads(session_state_path.read_text())
    else:
        session_state = {}

    session_state.update(
        {
            "session_id": f"ses-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "current_iteration": iteration_id,
            "current_phase": "phase_0",
            "current_task": None,
            "progress": {
                "total_tasks": 0,
                "completed": 0,
                "in_progress": 0,
                "pending": 0,
                "rework": 0,
                "failed": 0,
            },
            "consecutive_failures": 0,
        }
    )
    session_state_path.write_text(
        json.dumps(session_state, indent=2, ensure_ascii=False)
    )
    print(f"  更新: session-state.json")

    # 完成
    print()
    print("=" * 50)
    print(f"迭代 {iteration_id} 初始化完成")
    print()
    print("下一步:")
    print(f"  1. 启动 Claude Code，进入 Phase 1 需求深化")
    print(f"  2. Analyst Agent 将读取 requirement-raw.md 并生成 requirement-spec.md")
    print(f"  3. 或先运行基线测试: python dev-framework/scripts/run-baseline.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化新一轮迭代")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument(
        "--requirement", required=True, help="变更需求描述"
    )
    parser.add_argument(
        "--iteration-id", required=True, help="迭代 ID（如 iter-3）"
    )
    args = parser.parse_args()
    init_iteration(Path(args.project_dir), args.requirement, args.iteration_id)


if __name__ == "__main__":
    main()
