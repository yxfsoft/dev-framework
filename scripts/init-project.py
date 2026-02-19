#!/usr/bin/env python3
"""
init-project.py — 初始化新项目的开发框架

用法:
    python dev-framework/scripts/init-project.py \
        --project-dir "D:/new-project" \
        --requirement-doc "D:/new-project/docs/requirements.md" \
        --tech-stack "python,react"

执行后在目标项目中生成:
    .claude/agents/         Agent 定义文件
    .claude/dev-state/      开发状态目录
    .claude/CLAUDE.md       项目宪法（需手动定制）
    ARCHITECTURE.md         架构决策记录
    scripts/verify/         验收脚本目录
"""

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def get_framework_dir() -> Path:
    """获取框架根目录"""
    return Path(__file__).parent.parent


def init_project(project_dir: Path, requirement_doc: str, tech_stack: str) -> None:
    """初始化新项目"""
    framework_dir = get_framework_dir()
    project_dir = project_dir.resolve()

    print(f"初始化项目: {project_dir}")
    print(f"需求文档: {requirement_doc}")
    print(f"技术栈: {tech_stack}")
    print()

    # 1. 创建目录结构
    dirs = [
        ".claude/agents",
        ".claude/dev-state/iteration-0/tasks",
        ".claude/dev-state/iteration-0/verify",
        ".claude/dev-state/iteration-0/checkpoints",
        "scripts/verify",
        "tests/unit",
        "tests/integration",
        "config",
        "docs",
    ]

    for d in dirs:
        (project_dir / d).mkdir(parents=True, exist_ok=True)
        print(f"  创建目录: {d}")

    # 2. 复制 Agent 定义
    agents_src = framework_dir / "agents"
    agents_dst = project_dir / ".claude" / "agents"
    for agent_file in agents_src.glob("*.md"):
        shutil.copy2(agent_file, agents_dst / agent_file.name)
        print(f"  复制 Agent: {agent_file.name}")

    # 3. 生成 session-state.json
    session_state = {
        "session_id": f"ses-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "mode": "interactive",
        "current_iteration": "iteration-0",
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
        "last_checkpoint": "",
        "consecutive_failures": 0,
        "agents": {"active": [], "idle": []},
    }
    state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
    state_path.write_text(json.dumps(session_state, indent=2, ensure_ascii=False))
    print(f"  生成: session-state.json")

    # 4. 生成 baseline.json（空基线）
    baseline = {
        "iteration": "iteration-0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": "",
        "test_results": {
            "l1_passed": 0,
            "l1_failed": 0,
            "l1_skipped": 0,
            "l2_passed": 0,
            "l2_failed": 0,
        },
        "lint_clean": True,
        "pre_existing_failures": [],
    }
    baseline_path = project_dir / ".claude" / "dev-state" / "baseline.json"
    baseline_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False))
    print(f"  生成: baseline.json")

    # 5. 生成 run-config.yaml（从 schemas/run-config.yaml 复制默认配置）
    run_config_src = framework_dir / "schemas" / "run-config.yaml"
    run_config_dst = project_dir / ".claude" / "dev-state" / "run-config.yaml"
    shutil.copy2(run_config_src, run_config_dst)
    print(f"  生成: run-config.yaml")

    # 6. 生成 manifest.json
    manifest = {
        "id": "iteration-0",
        "mode": "init",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requirement_doc": requirement_doc,
        "tech_stack": tech_stack.split(","),
        "phase": "phase_0",
        "last_checkpoint": "",
    }
    manifest_path = (
        project_dir / ".claude" / "dev-state" / "iteration-0" / "manifest.json"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"  生成: iteration-0/manifest.json")

    # 7. 生成空文件
    empty_files = {
        ".claude/dev-state/experience-log.md": "# 经验教训日志\n\n> 发现的坑点和最佳实践记录于此。\n\n---\n",
        ".claude/dev-state/iteration-0/requirement-raw.md": f"# 原始需求\n\n需求文档路径: `{requirement_doc}`\n\n请参阅需求文档。\n",
        ".claude/dev-state/iteration-0/decisions.md": "# 关键决策日志\n\n> 记录开发过程中的关键技术决策。\n\n---\n",
    }
    for rel_path, content in empty_files.items():
        file_path = project_dir / rel_path
        file_path.write_text(content, encoding="utf-8")
        print(f"  生成: {rel_path}")

    # 8. 生成 CLAUDE.md（基于模板，替换已知变量，其余需手动填写）
    claude_md_path = project_dir / ".claude" / "CLAUDE.md"
    if not claude_md_path.exists():
        tmpl_path = framework_dir / "templates" / "project" / "CLAUDE.md.tmpl"
        if tmpl_path.exists():
            content = tmpl_path.read_text(encoding="utf-8")
            content = content.replace("{{PROJECT_NAME}}", project_dir.name)
            content = content.replace("{{TECH_STACK}}", tech_stack)
            # 以下占位符需要用户手动填写
            # {{PROJECT_DESCRIPTION}}, {{PROJECT_OVERVIEW}}, {{PROJECT_URL}},
            # {{PACKAGE_MANAGERS}}, {{CODE_STYLE}}, {{DIRECTORY_STRUCTURE}},
            # {{SECURITY_POLICY}}
            claude_md_path.write_text(content, encoding="utf-8")
        else:
            claude_md_path.write_text(
                f"# CLAUDE.md — {project_dir.name}\n\n"
                f"> 请基于 dev-framework/templates/project/CLAUDE.md.tmpl 模板，\n"
                f"> 结合项目实际情况定制此文件。\n\n"
                f"技术栈: {tech_stack}\n"
                f"需求文档: {requirement_doc}\n",
                encoding="utf-8",
            )
        print(f"  生成: CLAUDE.md (需手动定制 {{VARIABLE}} 占位符)")

    # 9. 生成 ARCHITECTURE.md
    arch_path = project_dir / "ARCHITECTURE.md"
    if not arch_path.exists():
        arch_src = framework_dir / "templates" / "project" / "ARCHITECTURE.md.tmpl"
        content = arch_src.read_text(encoding="utf-8")
        content = content.replace("{{PROJECT_NAME}}", project_dir.name)
        arch_path.write_text(content, encoding="utf-8")
        print(f"  生成: ARCHITECTURE.md")

    # 10. 生成 default.yaml
    config_path = project_dir / "config" / "default.yaml"
    if not config_path.exists():
        config_path.write_text(
            f"# {project_dir.name} 默认配置\n\n"
            f"# 本地覆盖请使用 config/local.yaml（不入 Git）\n",
            encoding="utf-8",
        )
        print(f"  生成: config/default.yaml")

    # 完成
    print()
    print("=" * 50)
    print(f"项目初始化完成: {project_dir}")
    print()
    print("下一步:")
    print(f"  1. 定制 .claude/CLAUDE.md（参考模板）")
    print(f"  2. 将需求文档放入 docs/ 目录")
    print(f"  3. 启动 Claude Code，开始 Phase 1 需求深化")
    print(f"  4. 或运行: python dev-framework/scripts/init-iteration.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化新项目的开发框架")
    parser.add_argument(
        "--project-dir", required=True, help="目标项目目录路径"
    )
    parser.add_argument(
        "--requirement-doc",
        required=True,
        help="需求文档路径（相对于项目目录或绝对路径）",
    )
    parser.add_argument(
        "--tech-stack",
        required=True,
        help="技术栈，逗号分隔（如 python,react,fastapi）",
    )
    args = parser.parse_args()
    init_project(Path(args.project_dir), args.requirement_doc, args.tech_stack)


if __name__ == "__main__":
    main()
