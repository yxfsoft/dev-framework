#!/usr/bin/env python3
"""
init-iteration.py — 在已有项目中初始化新一轮迭代

用法:
    python dev-framework/scripts/init-iteration.py \
        --project-dir "<项目路径>" \
        --requirement "修复搜索超时；新增批量导入" \
        --iteration-id "iter-3"

执行后在项目中新增:
    .claude/dev-state/iter-{id}/
        ├── manifest.json
        ├── requirement-raw.md
        ├── tasks/
        ├── verify/
        ├── checkpoints/
        └── decisions.md
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加 scripts 目录到 path 以导入 fw_utils
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import validate_manifest, validate_safe_id

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def check_stale_iterations(dev_state_dir: Path):
    """检测并提示清理失败的旧迭代（FIX-19）。"""
    if not dev_state_dir.exists():
        print(f"  [ERROR] dev-state 目录不存在: {dev_state_dir}")
        return
    for d in dev_state_dir.iterdir():
        if not d.is_dir():
            continue
        if not (d.name.startswith("iter-") or d.name.startswith("iteration-")):
            continue
        manifest = d / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if data.get("phase") == "phase_0":
                    tasks_dir = d / "tasks"
                    tasks = list(tasks_dir.glob("*.yaml")) if tasks_dir.exists() else []
                    if not tasks:
                        print(f"  [WARN] 发现空迭代 {d.name}（phase_0，无任务），建议删除")
            except Exception as e:
                print(f"  [WARN] manifest.json 解析失败 ({d.name}): {e}")
        # 检测命名不一致（iteration-0 是 init-project 生成的旧命名，保留兼容）
        if d.name.startswith("iteration-") and not d.name == "iteration-0":
            print(f"  [WARN] 发现旧命名格式 {d.name}，建议统一为 iter-N 格式")


def _find_previous_iteration(dev_state: Path, current_iter_id: str) -> str | None:
    """找到当前迭代的上一轮迭代 ID。"""
    # 提取当前迭代编号
    match = re.match(r"iter-(\d+)", current_iter_id)
    if not match:
        return None
    current_num = int(match.group(1))
    if current_num <= 0:
        return None
    prev_id = f"iter-{current_num - 1}"
    if (dev_state / prev_id).is_dir():
        return prev_id
    return None


def _collect_backlog(dev_state: Path, current_iter_id: str) -> list[dict]:
    """扫描上一轮迭代的 task YAML，收集 status 非 PASS 的任务。

    返回 [{id, title, status, iteration, reason}]
    """
    if yaml is None:
        return []

    prev_iter_id = _find_previous_iteration(dev_state, current_iter_id)
    if not prev_iter_id:
        return []

    tasks_dir = dev_state / prev_iter_id / "tasks"
    if not tasks_dir.exists():
        return []

    backlog = []
    for task_file in sorted(tasks_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(task_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not data or not isinstance(data, dict):
            continue

        status = data.get("status", "pending")
        if status == "PASS":
            continue  # 已完成，不纳入 backlog

        task_id = data.get("id", task_file.stem)
        title = data.get("title", "")
        reason = ""
        if status == "blocked":
            depends = data.get("depends", [])
            reason = f"依赖 {', '.join(depends)}" if depends else "blocked"
        elif status in ("rework", "FAIL"):
            reason = "验收/审查未通过"
        elif status == "timeout":
            reason = "执行超时"
        elif status in ("pending", "in_progress", "ready_for_verify", "ready_for_review"):
            reason = f"上轮未完成 (status={status})"
        else:
            reason = f"status={status}"

        backlog.append({
            "id": task_id,
            "title": title,
            "status": status,
            "iteration": prev_iter_id,
            "reason": reason,
        })

    return backlog


def _generate_backlog_md(items: list[dict], new_iter_id: str, prev_iter_id: str) -> str:
    """生成 Markdown 格式的 backlog 文件。"""
    lines = [
        f"# 延迟项 (Backlog) — {new_iter_id}",
        f"> 以下项目从 {prev_iter_id} 延续。Leader 须在 Phase 1 决定处理方式。",
        "",
        "| CR | 标题 | 上轮状态 | 原因 |",
        "|----|------|----------|------|",
    ]
    for item in items:
        lines.append(
            f"| {item['id']} | {item['title']} | {item['status']} | {item['reason']} |"
        )
    lines.extend([
        "",
        "## 处理决策",
    ])
    for item in items:
        lines.append(f"- [ ] {item['id']}: (纳入 / 推迟 / 取消)")
    lines.append("")
    return "\n".join(lines)


def init_iteration(
    project_dir: Path, requirement: str, iteration_id: str
) -> None:
    """初始化新一轮迭代"""
    project_dir = project_dir.resolve()
    dev_state = project_dir / ".claude" / "dev-state"

    if not dev_state.exists():
        print(f"错误: {dev_state} 不存在。请先运行 init-project.py 初始化项目。")
        return

    # FIX-19: 检测旧迭代残留
    print("检查现有迭代状态...")
    check_stale_iterations(dev_state)

    iter_dir = dev_state / iteration_id

    if iter_dir.exists():
        print(f"错误: {iter_dir} 已存在。请使用不同的 iteration-id。")
        return

    # FIX-19: 统一命名检查
    if not iteration_id.startswith("iter-"):
        print(f"[WARN] 建议使用 iter-N 格式（如 iter-3），当前: {iteration_id}")

    print(f"初始化迭代: {iteration_id}")
    print(f"项目: {project_dir}")
    print(f"需求: {requirement[:100]}{'...' if len(requirement) > 100 else ''}")
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
    # C2: 写入前校验 manifest 完整性（仅 WARN，不阻断）
    errors = validate_manifest(manifest)
    if errors:
        for e in errors:
            print(f"  [WARN] manifest 校验: {e}")
    manifest_path = iter_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
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

    # 4. 收集上一轮延迟项 (Backlog)
    backlog_items = _collect_backlog(dev_state, iteration_id)
    prev_iter_id = _find_previous_iteration(dev_state, iteration_id)

    if backlog_items and prev_iter_id:
        # 生成 backlog.md
        backlog_md = _generate_backlog_md(backlog_items, iteration_id, prev_iter_id)
        backlog_path = iter_dir / "backlog.md"
        backlog_path.write_text(backlog_md, encoding="utf-8")
        print(f"  生成: backlog.md（{len(backlog_items)} 个延迟项来自 {prev_iter_id}）")

        # 生成 decisions.md 时插入延迟项引用
        decisions_path = iter_dir / "decisions.md"
        decisions_content = (
            f"# 关键决策日志 — {iteration_id}\n\n"
            f"> 记录本轮迭代中的关键技术决策。\n\n"
            f"## 延迟项处理\n\n"
            f"> 来自 {prev_iter_id} 的 {len(backlog_items)} 个延迟项，详见 [backlog.md](backlog.md)。\n\n"
        )
        for item in backlog_items:
            decisions_content += f"- [ ] {item['id']} ({item['title']}): (纳入 / 推迟 / 取消)\n"
        decisions_content += "\n---\n"
        decisions_path.write_text(decisions_content, encoding="utf-8")
        print(f"  生成: decisions.md（含延迟项处理 checklist）")
    else:
        # 无延迟项，生成空 decisions.md
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
        session_state = json.loads(session_state_path.read_text(encoding="utf-8"))
    else:
        session_state = {}

    # M52: 合并更新，保留现有字段（如 mode, started_at, agents）
    now_iso = datetime.now(timezone.utc).isoformat()
    session_state["session_id"] = f"ses-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    session_state["last_updated"] = now_iso
    session_state.setdefault("started_at", now_iso)
    session_state.setdefault("mode", "interactive")
    session_state["current_iteration"] = iteration_id
    session_state["current_phase"] = "phase_0"
    session_state["current_task"] = None
    # 合并更新 progress，保留用户可能自定义的其他字段
    session_state.setdefault("progress", {})
    session_state["progress"].update({
        "total_tasks": 0,
        "completed": 0,
        "in_progress": 0,
        "pending": 0,
        "ready_for_verify": 0,
        "ready_for_review": 0,
        "rework": 0,
        "failed": 0,
        "blocked": 0,
        "timeout": 0,
    })
    session_state["consecutive_failures"] = 0
    session_state_path.write_text(
        json.dumps(session_state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  更新: session-state.json")

    # 完成
    print()
    print("=" * 50)
    print(f"迭代 {iteration_id} 初始化完成")
    print()
    print("下一步:")
    print(f"  1. 启动 Claude Code，进入 Phase 1 需求深化")
    print(f"  2. analyst 子代理将读取 requirement-raw.md 并生成 requirement-spec.md")
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
    validate_safe_id(args.iteration_id, "iteration-id")
    init_iteration(Path(args.project_dir), args.requirement, args.iteration_id)


if __name__ == "__main__":
    main()
