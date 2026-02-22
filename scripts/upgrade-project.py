#!/usr/bin/env python3
"""
upgrade-project.py — 将已有项目升级到 dev-framework v4.0

用法:
    python dev-framework/scripts/upgrade-project.py \
        --project-dir "<项目路径>"

    # 仅预览变更，不实际执行
    python dev-framework/scripts/upgrade-project.py \
        --project-dir "<项目路径>" --dry-run

    # 跳过备份
    python dev-framework/scripts/upgrade-project.py \
        --project-dir "<项目路径>" --no-backup

    # 强制重新执行已完成的步骤
    python dev-framework/scripts/upgrade-project.py \
        --project-dir "<项目路径>" --force

执行后:
    1. 自动检测当前框架版本
    2. 备份将修改的文件
    3. 按序执行升级迁移（25 步：基础 15 步 + v3.0 新增 5 步 + v4.0 新增 5 步）
    4. 写入版本标记 .framework-version = "4.0"
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ── 框架内部导入 ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import (
    detect_toolchain,
    load_run_config,
    load_session_state,
    load_baseline,
    load_task_yaml,
    save_task_yaml,
    get_framework_dir,
)

# init-project.py 含连字符，无法直接 import，使用 importlib
_init_spec = importlib.util.spec_from_file_location(
    "init_project", Path(__file__).resolve().parent / "init-project.py"
)
if _init_spec is None or _init_spec.loader is None:
    print("[ERROR] init-project.py 未找到，upgrade-project.py 无法工作")
    sys.exit(1)
_init_module = importlib.util.module_from_spec(_init_spec)
_init_spec.loader.exec_module(_init_module)
_setup_git_hooks = _init_module._setup_git_hooks
append_gitignore = _init_module.append_gitignore

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

TARGET_VERSION = "4.0"


# ============================================================
# 数据类
# ============================================================

@dataclass
class MigrateResult:
    status: str       # 'applied' | 'skipped' | 'error'
    message: str
    changes: int = 0


@dataclass
class UpgradeContext:
    project_dir: Path
    dev_state: Path
    dry_run: bool
    force: bool
    verbose: bool
    no_backup: bool
    current_version: str = ""
    backup_dir: Path | None = None
    results: list[tuple[str, MigrateResult]] = field(default_factory=list)


# ============================================================
# 工具函数
# ============================================================

def _log(ctx: UpgradeContext, msg: str) -> None:
    """verbose 模式下的详细日志。"""
    if ctx.verbose:
        print(f"  [VERBOSE] {msg}")


def _find_iter_dirs(dev_state: Path) -> list[Path]:
    """查找所有迭代目录（iter-* 和 iteration-*）。"""
    dirs = []
    if dev_state.exists():
        for d in sorted(dev_state.iterdir()):
            if d.is_dir() and (d.name.startswith("iter-") or d.name.startswith("iteration-")):
                dirs.append(d)
    return dirs


def _find_task_files(dev_state: Path) -> list[Path]:
    """查找所有迭代目录下的 task YAML 文件。"""
    files = []
    for iter_dir in _find_iter_dirs(dev_state):
        tasks_dir = iter_dir / "tasks"
        if tasks_dir.exists():
            files.extend(sorted(tasks_dir.glob("*.yaml")))
    return files


# ============================================================
# Step 1: preflight_check
# ============================================================

def migrate_preflight_check(ctx: UpgradeContext) -> MigrateResult:
    """检查 .claude/dev-state/ 存在、PyYAML 可用。"""
    errors = []

    if not ctx.dev_state.exists():
        errors.append(f".claude/dev-state/ 不存在: {ctx.dev_state}")

    if yaml is None:
        errors.append("PyYAML 未安装。运行: pip install PyYAML>=6.0")

    if errors:
        return MigrateResult("error", "; ".join(errors))

    return MigrateResult("applied", "环境检查通过")


# ============================================================
# Step 2: detect_current_version
# ============================================================

def migrate_detect_current_version(ctx: UpgradeContext) -> MigrateResult:
    """读取 .framework-version 或特征检测当前版本。"""
    version_file = ctx.dev_state / ".framework-version"

    if version_file.exists():
        ver = version_file.read_text(encoding="utf-8").strip()
        ctx.current_version = ver
        if ver == TARGET_VERSION and not ctx.force:
            return MigrateResult("skipped", f"已是 v{TARGET_VERSION}，无需升级（用 --force 强制）")
        return MigrateResult("applied", f"检测到版本标记: v{ver}")

    # 特征检测：检查是否有 iteration-* 目录（旧版命名）
    has_old_dirs = False
    if ctx.dev_state.exists():
        has_old_dirs = any(
            d.name.startswith("iteration-")
            for d in ctx.dev_state.iterdir() if d.is_dir()
        )
    # 特征检测：检查 run-config.yaml 是否缺少 toolchain
    config = load_run_config(ctx.project_dir)
    has_toolchain = "toolchain" in config

    # v4.0 特征检测：检查 .claude/agents/ 是否存在
    agents_dir = ctx.project_dir / ".claude" / "agents"
    if agents_dir.exists() and (agents_dir / "analyst.md").exists():
        ctx.current_version = "4.0"
        return MigrateResult("applied", "特征检测: .claude/agents/ 存在，判定为 v4.0")

    # v3.0 特征检测：检查 .claude/CLAUDE.md 是否包含合并标记
    claude_md = ctx.project_dir / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        try:
            claude_content = claude_md.read_text(encoding="utf-8")
            if "Dev-Framework 运行时手册 v3.0" in claude_content:
                ctx.current_version = "3.0"
                return MigrateResult("applied", "特征检测: CLAUDE.md 包含 v3.0 运行时手册")
        except Exception:
            pass

    if has_old_dirs:
        ctx.current_version = "pre-2.6"
        return MigrateResult("applied", "特征检测: 发现 iteration-* 目录，判定为 pre-2.6")
    elif not has_toolchain and config:
        ctx.current_version = "pre-2.6"
        return MigrateResult("applied", "特征检测: run-config.yaml 缺少 toolchain，判定为 pre-2.6")
    else:
        ctx.current_version = "unknown"
        return MigrateResult("applied", "未找到版本标记，按全量升级处理")


# ============================================================
# Step 3: create_backup
# ============================================================

def migrate_create_backup(ctx: UpgradeContext) -> MigrateResult:
    """备份将修改的文件到 .upgrade-backup-{timestamp}/。"""
    if ctx.no_backup:
        return MigrateResult("skipped", "用户指定 --no-backup，跳过备份")

    if ctx.dry_run:
        return MigrateResult("skipped", "[dry-run] 跳过备份")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = ctx.dev_state / f".upgrade-backup-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ctx.backup_dir = backup_dir

    # 收集需要备份的文件
    files_to_backup = []

    # session-state.json
    ss = ctx.dev_state / "session-state.json"
    if ss.exists():
        files_to_backup.append(ss)

    # baseline.json
    bl = ctx.dev_state / "baseline.json"
    if bl.exists():
        files_to_backup.append(bl)

    # run-config.yaml
    rc = ctx.dev_state / "run-config.yaml"
    if rc.exists():
        files_to_backup.append(rc)

    # experience-log.md
    el = ctx.dev_state / "experience-log.md"
    if el.exists():
        files_to_backup.append(el)

    # 所有任务 YAML
    files_to_backup.extend(_find_task_files(ctx.dev_state))

    # manifest.json
    for iter_dir in _find_iter_dirs(ctx.dev_state):
        mf = iter_dir / "manifest.json"
        if mf.exists():
            files_to_backup.append(mf)

    # CLAUDE.md（两个位置）
    for claude_md in [
        ctx.project_dir / ".claude" / "CLAUDE.md",
        ctx.project_dir / "CLAUDE.md",
    ]:
        if claude_md.exists():
            files_to_backup.append(claude_md)

    # Agent 文件
    agents_dir = ctx.project_dir / ".claude" / "agents"
    if agents_dir.exists():
        files_to_backup.extend(agents_dir.glob("*.md"))

    # .gitignore
    gi = ctx.project_dir / ".gitignore"
    if gi.exists():
        files_to_backup.append(gi)

    # context-snapshot.md
    cs = ctx.dev_state / "context-snapshot.md"
    if cs.exists():
        files_to_backup.append(cs)

    # 执行备份
    manifest_lines = []
    for src in files_to_backup:
        rel = src.relative_to(ctx.project_dir)
        dst = backup_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        manifest_lines.append(str(rel))
        _log(ctx, f"备份: {rel}")

    # 写入 manifest.txt
    (backup_dir / "manifest.txt").write_text(
        f"# 升级备份 — {timestamp}\n"
        f"# 共 {len(manifest_lines)} 个文件\n\n"
        + "\n".join(manifest_lines) + "\n",
        encoding="utf-8",
    )

    return MigrateResult("applied", f"已备份 {len(manifest_lines)} 个文件到 {backup_dir.name}/", len(manifest_lines))


# ============================================================
# Step 4: BC-1 rename_iteration_dirs
# ============================================================

def migrate_rename_iteration_dirs(ctx: UpgradeContext) -> MigrateResult:
    """将 iteration-* 目录重命名为 iter-*，并更新相关引用。"""
    old_dirs = [
        d for d in ctx.dev_state.iterdir()
        if d.is_dir() and d.name.startswith("iteration-")
    ] if ctx.dev_state.exists() else []

    if not old_dirs:
        return MigrateResult("skipped", "未发现 iteration-* 目录")

    changes = 0
    for old_dir in sorted(old_dirs):
        suffix = old_dir.name.replace("iteration-", "")
        new_name = f"iter-{suffix}"
        new_dir = ctx.dev_state / new_name

        if new_dir.exists():
            _log(ctx, f"目标已存在，跳过: {new_name}")
            continue

        if ctx.dry_run:
            print(f"    [dry-run] 重命名: {old_dir.name} -> {new_name}")
            changes += 1
            continue

        old_dir.rename(new_dir)
        _log(ctx, f"重命名: {old_dir.name} -> {new_name}")
        changes += 1

        # 更新 manifest.json 中的 id
        manifest_path = new_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("id", "").startswith("iteration-"):
                manifest["id"] = new_name
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                _log(ctx, f"更新 manifest.json id: {new_name}")

    # 更新 session-state.json 的 current_iteration
    if not ctx.dry_run:
        ss_path = ctx.dev_state / "session-state.json"
        if ss_path.exists():
            ss = json.loads(ss_path.read_text(encoding="utf-8"))
            cur = ss.get("current_iteration", "")
            if cur.startswith("iteration-"):
                ss["current_iteration"] = cur.replace("iteration-", "iter-")
                ss_path.write_text(
                    json.dumps(ss, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                _log(ctx, f"更新 session-state.json current_iteration")
                changes += 1

    # 更新所有 task YAML 的 iteration 字段
    if not ctx.dry_run:
        for task_path in _find_task_files(ctx.dev_state):
            task = load_task_yaml(task_path)
            if task and isinstance(task.get("iteration"), str) and task["iteration"].startswith("iteration-"):
                task["iteration"] = task["iteration"].replace("iteration-", "iter-")
                save_task_yaml(task_path, task)
                _log(ctx, f"更新任务 iteration 字段: {task_path.name}")
                changes += 1

    return MigrateResult("applied", f"重命名 {len(old_dirs)} 个目录", changes)


# ============================================================
# Step 5: session_state_fields
# ============================================================

def migrate_session_state_fields(ctx: UpgradeContext) -> MigrateResult:
    """补齐 session-state.json 的 progress 新字段。"""
    ss_path = ctx.dev_state / "session-state.json"
    if not ss_path.exists():
        return MigrateResult("skipped", "session-state.json 不存在")

    ss = json.loads(ss_path.read_text(encoding="utf-8"))
    progress = ss.setdefault("progress", {})

    new_fields = {
        "ready_for_verify": 0,
        "ready_for_review": 0,
        "blocked": 0,
        "timeout": 0,
    }

    added = []
    for key, default in new_fields.items():
        if key not in progress:
            progress[key] = default
            added.append(key)

    if not added:
        return MigrateResult("skipped", "progress 字段已是最新")

    if ctx.dry_run:
        return MigrateResult("skipped", f"[dry-run] 将补齐: {', '.join(added)}")

    ss_path.write_text(
        json.dumps(ss, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return MigrateResult("applied", f"补齐 progress 字段: {', '.join(added)}", len(added))


# ============================================================
# Step 6: baseline_fields
# ============================================================

def migrate_baseline_fields(ctx: UpgradeContext) -> MigrateResult:
    """补齐 baseline.json 的 test_results.l2_skipped 字段。"""
    bl_path = ctx.dev_state / "baseline.json"
    if not bl_path.exists():
        return MigrateResult("skipped", "baseline.json 不存在")

    bl = json.loads(bl_path.read_text(encoding="utf-8"))
    test_results = bl.setdefault("test_results", {})

    if "l2_skipped" in test_results:
        return MigrateResult("skipped", "l2_skipped 已存在")

    if ctx.dry_run:
        return MigrateResult("skipped", "[dry-run] 将补齐 l2_skipped: 0")

    test_results.setdefault("l2_skipped", 0)
    bl_path.write_text(
        json.dumps(bl, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return MigrateResult("applied", "补齐 test_results.l2_skipped: 0", 1)


# ============================================================
# Step 7: run_config
# ============================================================

def migrate_run_config(ctx: UpgradeContext) -> MigrateResult:
    """补齐 run-config.yaml 的 toolchain/iteration_mode/hooks 配置块。"""
    rc_path = ctx.dev_state / "run-config.yaml"
    if not rc_path.exists():
        return MigrateResult("skipped", "run-config.yaml 不存在")

    config = yaml.safe_load(rc_path.read_text(encoding="utf-8")) or {}

    added = []

    # toolchain
    if "toolchain" not in config:
        config["toolchain"] = {
            "test_runner": "auto",
            "linter": "auto",
            "formatter": "auto",
            "python": "auto",
        }
        added.append("toolchain")
    else:
        tc = config["toolchain"]
        for key in ["test_runner", "linter", "formatter", "python"]:
            if key not in tc:
                tc[key] = "auto"
                added.append(f"toolchain.{key}")

    # iteration_mode
    if "iteration_mode" not in config:
        config["iteration_mode"] = "standard"
        added.append("iteration_mode")

    # hooks
    if "hooks" not in config:
        config["hooks"] = {
            "commit_message_pattern": "default",
            "commit_message_regex": "",
        }
        added.append("hooks")
    else:
        hk = config["hooks"]
        hk.setdefault("commit_message_pattern", "default")
        hk.setdefault("commit_message_regex", "")

    if not added:
        return MigrateResult("skipped", "run-config.yaml 已包含所有 v2.6 配置块")

    if ctx.dry_run:
        return MigrateResult("skipped", f"[dry-run] 将补齐: {', '.join(added)}")

    rc_path.write_text(
        yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return MigrateResult("applied", f"补齐配置块: {', '.join(added)}", len(added))


# ============================================================
# Step 8: BC-5 acceptance_criteria list->dict
# ============================================================

def migrate_acceptance_criteria(ctx: UpgradeContext) -> MigrateResult:
    """将 acceptance_criteria 转为 v3.0 schema 格式（functional 分组 + 任务 ID 前缀）。

    支持三种输入格式：
    1. 旧 list 格式: ["条件1", "条件2"]
       → {functional: [{id: "XX-AC1", desc: "条件1", status: "FAIL"}, ...]}
    2. 旧 dict 格式: {"AC-1": {text: "...", met: true/false}}
       → {functional: [{id: "XX-AC1", desc: "...", status: "PASS"/"FAIL"}, ...]}
    3. 已是新格式（含 functional key）→ 跳过
    """
    task_files = _find_task_files(ctx.dev_state)
    if not task_files:
        return MigrateResult("skipped", "未找到任务文件")

    changes = 0
    for task_path in task_files:
        task = load_task_yaml(task_path)
        if not task:
            continue
        ac = task.get("acceptance_criteria")
        if ac is None:
            continue

        # 已是新格式（含任一新版维度 key）→ 跳过
        _NEW_FORMAT_KEYS = {"functional", "robustness", "performance", "ux_states", "ux_interaction", "security", "observability"}
        if isinstance(ac, dict) and any(k in ac for k in _NEW_FORMAT_KEYS):
            _log(ctx, f"已是新格式，跳过: {task_path.name}")
            continue

        # 从任务 id 字段提取前缀（如 "CR-001" → "CR-001"）
        task_id = task.get("id", "TASK")

        functional_items = []

        if isinstance(ac, list):
            if not ac:  # 空列表，跳过转换
                _log(ctx, f"acceptance_criteria 为空列表，跳过: {task_path.name}")
                continue
            # 格式 1: 旧 list 格式
            for i, item in enumerate(ac, 1):
                ac_id = f"{task_id}-AC{i}"
                if isinstance(item, str):
                    desc = item
                elif isinstance(item, dict):
                    desc = item.get("text", item.get("desc", str(item)))
                else:
                    desc = str(item)
                functional_items.append({
                    "id": ac_id,
                    "desc": desc,
                    "status": "FAIL",
                })
        elif isinstance(ac, dict):
            # 格式 2: 旧 dict 格式 {"AC-1": {text: "...", met: true/false}}
            for i, (key, val) in enumerate(ac.items(), 1):
                ac_id = f"{task_id}-AC{i}"
                if isinstance(val, dict):
                    desc = val.get("text", val.get("desc", str(val)))
                    met = val.get("met", False)
                    status = "PASS" if met else "FAIL"
                else:
                    desc = str(val)
                    status = "FAIL"
                functional_items.append({
                    "id": ac_id,
                    "desc": desc,
                    "status": status,
                })
        else:
            _log(ctx, f"未知 acceptance_criteria 类型，跳过: {task_path.name}")
            continue

        new_ac = {"functional": functional_items}

        if ctx.dry_run:
            print(f"    [dry-run] 转换: {task_path.name} ({len(functional_items)} 项)")
            changes += 1
            continue

        task["acceptance_criteria"] = new_ac
        save_task_yaml(task_path, task)
        _log(ctx, f"转换 acceptance_criteria: {task_path.name}")
        changes += 1

    if changes == 0:
        return MigrateResult("skipped", "所有任务的 acceptance_criteria 已是新格式")
    return MigrateResult("applied", f"转换 {changes} 个任务文件", changes)


# ============================================================
# Step 9: BC-6 add_priority（字符串插入法）
# ============================================================

def migrate_add_priority(ctx: UpgradeContext) -> MigrateResult:
    """在 task YAML 的 type: 行后插入 priority: "P1"（字符串插入，保留注释）。"""
    task_files = _find_task_files(ctx.dev_state)
    if not task_files:
        return MigrateResult("skipped", "未找到任务文件")

    changes = 0
    for task_path in task_files:
        content = task_path.read_text(encoding="utf-8")

        # 如果已有 priority 字段，跳过
        if re.search(r"^priority\s*:", content, re.MULTILINE):
            _log(ctx, f"已有 priority，跳过: {task_path.name}")
            continue

        # 在 type: 行后插入 priority: "P1"
        match = re.search(r"^(type\s*:.+)$", content, re.MULTILINE)
        if not match:
            _log(ctx, f"未找到 type: 行，跳过: {task_path.name}")
            continue

        if ctx.dry_run:
            print(f"    [dry-run] 添加 priority: {task_path.name}")
            changes += 1
            continue

        insert_pos = match.end()
        new_content = content[:insert_pos] + '\npriority: "P1"' + content[insert_pos:]
        task_path.write_text(new_content, encoding="utf-8")
        _log(ctx, f"添加 priority: {task_path.name}")
        changes += 1

    if changes == 0:
        return MigrateResult("skipped", "所有任务已有 priority 字段")
    return MigrateResult("applied", f"为 {changes} 个任务添加 priority", changes)


# ============================================================
# Step 10: BC-9 review_issues 格式规范化
# ============================================================

def migrate_review_issues(ctx: UpgradeContext) -> MigrateResult:
    """将 review_result.issues 中的纯字符串转为 {severity, desc} 格式。"""
    task_files = _find_task_files(ctx.dev_state)
    if not task_files:
        return MigrateResult("skipped", "未找到任务文件")

    changes = 0
    for task_path in task_files:
        task = load_task_yaml(task_path)
        if not task:
            continue
        review = task.get("review_result")
        if not isinstance(review, dict):
            continue
        issues = review.get("issues")
        if not isinstance(issues, list):
            continue

        converted = False
        new_issues = []
        for item in issues:
            if isinstance(item, str):
                new_issues.append({"severity": "info", "desc": item})
                converted = True
            else:
                new_issues.append(item)

        if not converted:
            continue

        if ctx.dry_run:
            print(f"    [dry-run] 规范化 review_issues: {task_path.name}")
            changes += 1
            continue

        review["issues"] = new_issues
        save_task_yaml(task_path, task)
        _log(ctx, f"规范化 review_issues: {task_path.name}")
        changes += 1

    if changes == 0:
        return MigrateResult("skipped", "所有任务的 review_issues 已是规范格式")
    return MigrateResult("applied", f"规范化 {changes} 个任务的 review_issues", changes)


# ============================================================
# Step 11: claude_md — 插入 5.1/5.2 章节
# ============================================================

_SECTION_5_1 = """\

---

## 5.1 已知坑点与最佳实践

<!-- v2.6 FIX-05: 替代已废弃的 experience-log.md -->
<!-- 开发过程中发现的问题和解决方案，由 Developer Agent 自动维护 -->
<!-- 此章节自动加载为系统提示，无需手动读取 -->
"""

_SECTION_5_2 = """\

---

## 5.2 Git 提交规范

<!-- 框架文件禁止提交 Git -->

以下文件/目录**禁止**提交到 Git（.gitignore 已自动配置）：
- `.claude/dev-state/` — 框架状态文件
- `iter-*/` / `iteration-*/` — 迭代记录
- 原因：双端开发场景下框架文件会产生冲突
"""


def migrate_claude_md(ctx: UpgradeContext) -> MigrateResult:
    """合并插入 5.1/5.2 章节到 CLAUDE.md。"""
    # 定位 CLAUDE.md
    claude_md_path = ctx.project_dir / ".claude" / "CLAUDE.md"
    if not claude_md_path.exists():
        claude_md_path = ctx.project_dir / "CLAUDE.md"
    if not claude_md_path.exists():
        return MigrateResult("skipped", "未找到 CLAUDE.md")

    content = claude_md_path.read_text(encoding="utf-8")

    # 检查是否已包含 5.1
    if "已知坑点" in content and "5.1" in content:
        return MigrateResult("skipped", "CLAUDE.md 已包含 5.1 章节")

    # v3.0: 如果框架模板存在，由 Step 16 (generate_merged_claude_md) 统一处理
    fw_tmpl = get_framework_dir() / "templates" / "project" / "CLAUDE-framework.md.tmpl"
    if fw_tmpl.exists():
        return MigrateResult("skipped", "已是 v3.0 格式，由 Step 16 (generate_merged_claude_md) 处理")

    # 查找插入位置：在 "## 5. 开发框架" 章节的末尾（下一个 ## 之前）
    # 或者在包含 "开发框架" 的章节后
    insert_pos = None

    # 策略 1：找到 "## 5." 开头的章节，然后找下一个 "## 6." 或 "---\n\n## 6."
    match_5 = re.search(r"^## 5\..*$", content, re.MULTILINE)
    if match_5:
        # 找到下一个 ## 6. 之前的 ---
        match_next = re.search(r"\n---\s*\n+## 6\.", content[match_5.end():])
        if match_next:
            insert_pos = match_5.end() + match_next.start()
        else:
            # 找下一个同级标题
            match_next = re.search(r"\n## \d+\.", content[match_5.end():])
            if match_next:
                insert_pos = match_5.end() + match_next.start()

    # 策略 2：找包含 "开发框架" 的章节标题
    if insert_pos is None:
        match_fw = re.search(r"^## .*开发框架.*$", content, re.MULTILINE)
        if match_fw:
            match_next = re.search(r"\n## ", content[match_fw.end():])
            if match_next:
                insert_pos = match_fw.end() + match_next.start()
            else:
                insert_pos = len(content)

    if insert_pos is None:
        # 策略 3：追加到文件末尾
        insert_pos = len(content)

    if ctx.dry_run:
        return MigrateResult("skipped", f"[dry-run] 将在 CLAUDE.md 第 {content[:insert_pos].count(chr(10))+1} 行后插入 5.1/5.2")

    new_content = content[:insert_pos] + _SECTION_5_1 + _SECTION_5_2 + content[insert_pos:]
    claude_md_path.write_text(new_content, encoding="utf-8")
    return MigrateResult("applied", f"插入 5.1/5.2 章节到 {claude_md_path.relative_to(ctx.project_dir)}", 2)


# ============================================================
# Step 12: BC-3 experience_log 迁移
# ============================================================

_EXPERIENCE_DEPRECATED = """\
# 经验教训日志 (DEPRECATED)

> v2.6 起此文件已废弃。
> 经验教训请写入 CLAUDE.md 的「已知坑点与最佳实践」章节。
> 保留此文件以兼容旧版本，但不再主动使用。

---
"""


def migrate_experience_log(ctx: UpgradeContext) -> MigrateResult:
    """将 experience-log.md 内容迁移到 CLAUDE.md，然后替换为废弃声明。"""
    exp_path = ctx.dev_state / "experience-log.md"
    if not exp_path.exists():
        return MigrateResult("skipped", "experience-log.md 不存在")

    content = exp_path.read_text(encoding="utf-8").strip()

    # 检查是否已是废弃声明
    if "DEPRECATED" in content or "已废弃" in content:
        return MigrateResult("skipped", "experience-log.md 已是废弃状态")

    # 提取实质内容（去掉标题行和空行）
    lines = content.splitlines()
    substance = []
    for line in lines:
        stripped = line.strip()
        # 跳过标题和分隔线
        if stripped.startswith("# ") or stripped == "---" or stripped == "":
            continue
        substance.append(line)

    if not substance:
        # 无实质内容，直接替换
        if ctx.dry_run:
            return MigrateResult("skipped", "[dry-run] experience-log.md 无实质内容，将替换为废弃声明")
        exp_path.write_text(_EXPERIENCE_DEPRECATED, encoding="utf-8")
        return MigrateResult("applied", "experience-log.md 替换为废弃声明（无实质内容需迁移）", 1)

    # 有实质内容：追加到 CLAUDE.md 的 5.1 章节
    claude_md_path = ctx.project_dir / ".claude" / "CLAUDE.md"
    if not claude_md_path.exists():
        claude_md_path = ctx.project_dir / "CLAUDE.md"

    if ctx.dry_run:
        return MigrateResult("skipped", f"[dry-run] 将迁移 {len(substance)} 行到 CLAUDE.md")

    if claude_md_path.exists():
        claude_content = claude_md_path.read_text(encoding="utf-8")
        # 在 5.1 章节末尾追加
        match = re.search(r"(## 5\.1.*已知坑点.*\n)", claude_content)
        if match:
            # 找到 5.1 下一个 ## 或 --- 之前
            rest = claude_content[match.end():]
            next_section = re.search(r"\n---\s*\n+## |\n## ", rest)
            if next_section:
                insert_pos = match.end() + next_section.start()
            else:
                insert_pos = len(claude_content)

            migrated_block = (
                "\n<!-- 以下内容从 experience-log.md 自动迁移 (upgrade v2.6) -->\n"
                + "\n".join(substance) + "\n"
            )
            claude_content = claude_content[:insert_pos] + migrated_block + claude_content[insert_pos:]
            claude_md_path.write_text(claude_content, encoding="utf-8")

    # 替换 experience-log.md 为废弃声明
    exp_path.write_text(_EXPERIENCE_DEPRECATED, encoding="utf-8")
    return MigrateResult("applied", f"迁移 {len(substance)} 行经验到 CLAUDE.md，原文件已废弃", len(substance) + 1)


# ============================================================
# Step 13: agent_protocols — 全量覆盖
# ============================================================

def migrate_agent_protocols(ctx: UpgradeContext) -> MigrateResult:
    """v3.0: 清理项目中残留的 .claude/agents/ 目录（已由 Step 3 备份）。"""
    agents_dir = ctx.project_dir / ".claude" / "agents"
    if not agents_dir.exists():
        return MigrateResult("skipped", "项目中无 .claude/agents/ 目录")

    agent_files = list(agents_dir.glob("*.md"))
    if not agent_files:
        return MigrateResult("skipped", ".claude/agents/ 目录为空")

    if ctx.dry_run:
        return MigrateResult("skipped", f"[dry-run] 将删除 .claude/agents/（{len(agent_files)} 个文件）")

    shutil.rmtree(agents_dir)
    return MigrateResult("applied", f"删除 .claude/agents/（{len(agent_files)} 个文件，已由 Step 3 备份）", len(agent_files))


# ============================================================
# Step 14: BC-10 git_hooks — 重新生成
# ============================================================

def migrate_git_hooks(ctx: UpgradeContext) -> MigrateResult:
    """调用 init-project.py 的 _setup_git_hooks() 重新生成（传入工具链）。"""
    git_hooks_dir = ctx.project_dir / ".git" / "hooks"
    if not git_hooks_dir.exists():
        return MigrateResult("skipped", ".git/hooks/ 不存在，跳过（请先 git init）")

    if ctx.dry_run:
        return MigrateResult("skipped", "[dry-run] 将重新生成 Git hooks")

    config = load_run_config(ctx.project_dir)
    toolchain = detect_toolchain(ctx.project_dir, config)
    _setup_git_hooks(ctx.project_dir, toolchain=toolchain)
    return MigrateResult("applied", "重新生成 pre-commit / commit-msg / pre-push (shell+py 分离)", 6)


# ============================================================
# Step 15: gitignore
# ============================================================

def migrate_gitignore(ctx: UpgradeContext) -> MigrateResult:
    """调用 init-project.py 的 append_gitignore()。"""
    gitignore = ctx.project_dir / ".gitignore"
    marker = "# === dev-framework: 以下由框架自动生成，禁止手动修改 ==="

    if gitignore.exists() and marker in gitignore.read_text(encoding="utf-8"):
        return MigrateResult("skipped", ".gitignore 已包含框架规则")

    if ctx.dry_run:
        return MigrateResult("skipped", "[dry-run] 将追加 .gitignore 框架规则")

    append_gitignore(ctx.project_dir)
    return MigrateResult("applied", "追加 .gitignore 框架规则", 1)


# ============================================================
# Step 16: v3.0 generate_merged_claude_md
# ============================================================

def migrate_generate_merged_claude_md(ctx: UpgradeContext) -> MigrateResult:
    """从 CLAUDE-framework.md.tmpl 生成合并版 .claude/CLAUDE.md。"""
    try:
        return _generate_merged_claude_md_impl(ctx)
    except Exception as e:
        # 回退：执行 Step 11 的基本逻辑，确保 CLAUDE.md 至少得到更新
        print(f"    [WARN] generate_merged_claude_md 失败: {e}")
        print(f"    [WARN] 回退到基本 CLAUDE.md 更新（Step 11 逻辑）...")
        try:
            return _generate_merged_claude_md_fallback(ctx)
        except Exception as fallback_err:
            return MigrateResult("error", f"主逻辑和回退均失败: {e} / {fallback_err}")


def _generate_merged_claude_md_fallback(ctx: UpgradeContext) -> MigrateResult:
    """回退逻辑：执行 Step 11 的基本 CLAUDE.md 更新（插入 5.1/5.2 章节）。"""
    claude_md_path = ctx.project_dir / ".claude" / "CLAUDE.md"
    if not claude_md_path.exists():
        claude_md_path = ctx.project_dir / "CLAUDE.md"
    if not claude_md_path.exists():
        return MigrateResult("applied", "[fallback] 未找到 CLAUDE.md，跳过基本更新", 0)

    content = claude_md_path.read_text(encoding="utf-8")

    # 如果已包含 5.1 章节，无需重复插入
    if "已知坑点" in content and "5.1" in content:
        return MigrateResult("applied", "[fallback] CLAUDE.md 已包含 5.1 章节", 0)

    if ctx.dry_run:
        return MigrateResult("skipped", "[fallback][dry-run] 将插入 5.1/5.2 章节")

    # 查找插入位置
    insert_pos = None

    match_5 = re.search(r"^## 5\..*$", content, re.MULTILINE)
    if match_5:
        match_next = re.search(r"\n---\s*\n+## 6\.", content[match_5.end():])
        if match_next:
            insert_pos = match_5.end() + match_next.start()
        else:
            match_next = re.search(r"\n## \d+\.", content[match_5.end():])
            if match_next:
                insert_pos = match_5.end() + match_next.start()

    if insert_pos is None:
        match_fw = re.search(r"^## .*开发框架.*$", content, re.MULTILINE)
        if match_fw:
            match_next = re.search(r"\n## ", content[match_fw.end():])
            if match_next:
                insert_pos = match_fw.end() + match_next.start()
            else:
                insert_pos = len(content)

    if insert_pos is None:
        insert_pos = len(content)

    new_content = content[:insert_pos] + _SECTION_5_1 + _SECTION_5_2 + content[insert_pos:]
    claude_md_path.write_text(new_content, encoding="utf-8")
    return MigrateResult("applied", f"[fallback] 插入 5.1/5.2 章节到 {claude_md_path.relative_to(ctx.project_dir)}", 2)


def _generate_merged_claude_md_impl(ctx: UpgradeContext) -> MigrateResult:
    """generate_merged_claude_md 的主逻辑实现。"""
    claude_md_path = ctx.project_dir / ".claude" / "CLAUDE.md"
    if not claude_md_path.exists():
        claude_md_path = ctx.project_dir / "CLAUDE.md"

    # 检查是否已是 v3.0 合并版（--force 时强制重新生成）
    if claude_md_path.exists() and not ctx.force:
        content = claude_md_path.read_text(encoding="utf-8")
        if "Dev-Framework 运行时手册 v3.0" in content:
            return MigrateResult("skipped", "CLAUDE.md 已包含 v3.0 运行时手册")

    # 读取模板
    framework_dir = get_framework_dir()
    fw_tmpl = framework_dir / "templates" / "project" / "CLAUDE-framework.md.tmpl"
    if not fw_tmpl.exists():
        return MigrateResult("error", f"框架模板不存在: {fw_tmpl}")

    # 提取现有 CLAUDE.md 中的自定义坑点内容
    gotchas_content = ""
    if claude_md_path.exists():
        existing = claude_md_path.read_text(encoding="utf-8")
        # 尝试提取 5.1 或 十一 章节内容
        for pattern in [
            r"## 5\.1\s+已知坑点与最佳实践\s*\n(.*?)(?=\n---|\n## [0-9]|\n## [一-龥]|\Z)",
            r"## 十一、已知坑点与最佳实践\s*\n(.*?)(?=\n---|\n## |\Z)",
        ]:
            match = re.search(pattern, existing, re.DOTALL)
            if match:
                raw = match.group(1).strip()
                # 过滤掉纯注释行
                lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith("<!--")]
                if lines:
                    gotchas_content = "\n".join(lines)
                break

    if ctx.dry_run:
        msg = f"[dry-run] 将生成合并版 CLAUDE.md"
        if gotchas_content:
            msg += f"（保留 {len(gotchas_content.splitlines())} 行自定义坑点）"
        return MigrateResult("skipped", msg)

    # 生成合并版
    fw_content = fw_tmpl.read_text(encoding="utf-8")
    fw_content = fw_content.replace("{{FRAMEWORK_PATH}}", str(framework_dir))
    fw_content = fw_content.replace("{{PROJECT_GOTCHAS}}", gotchas_content)

    # 工具链命令替换：根据项目实际工具链替换 {{TEST_RUNNER}}
    config = load_run_config(ctx.project_dir)
    toolchain = detect_toolchain(ctx.project_dir, config)
    fw_content = fw_content.replace("{{TEST_RUNNER}}", toolchain["test_runner"])
    fw_content = fw_content.replace("{{PYTHON}}", toolchain["python"])

    # 保留已有的项目配置部分（如果有）
    target_path = ctx.project_dir / ".claude" / "CLAUDE.md"

    # 如果已有 CLAUDE.md 包含项目配置（非纯框架内容），保留项目配置 + 追加框架内容
    if target_path.exists():
        existing = target_path.read_text(encoding="utf-8")
        # 检查是否有项目特定配置（section 1-4, 6, 7）
        if "## 1. 项目概述" in existing or "## 项目概述" in existing:
            # 移除旧的框架章节（5.x, 8），保留项目配置
            # 简单策略：在已有内容后追加框架手册
            # 先移除旧框架引用
            cleaned = existing
            # 移除旧的上下文校准协议（section 8 到文件末尾）
            # 注意：re.DOTALL 使 .* 匹配换行符，会删除 section 8 之后的所有内容
            # 标准 CLAUDE.md 模板最多到 section 7，因此不会误删项目自定义内容
            cleaned = re.sub(
                r"\n---\s*\n+## 8\.\s*上下文校准协议.*$",
                "",
                cleaned,
                flags=re.DOTALL,
            )
            # 移除旧的 5.1/5.2 （框架相关内容）
            cleaned = re.sub(
                r"\n---\s*\n+## 5\.1\s+已知坑点.*?(?=\n---\s*\n+## [67]\.)",
                "",
                cleaned,
                flags=re.DOTALL,
            )
            cleaned = re.sub(
                r"\n---\s*\n+## 5\.2\s+Git 提交规范.*?(?=\n---\s*\n+## [67]\.)",
                "",
                cleaned,
                flags=re.DOTALL,
            )
            # 更新 section 5 为简短引用
            cleaned = re.sub(
                r"## 5\.\s*开发框架.*?(?=\n---\s*\n+## [67]\.)",
                "## 5. 开发框架\n\n本项目使用 dev-framework v3.0 管理。\n完整框架运行时手册已合并到 `.claude/CLAUDE.md`，作为系统提示自动加载。\n",
                cleaned,
                flags=re.DOTALL,
            )
            target_path.write_text(
                cleaned.rstrip() + "\n\n---\n\n" + fw_content,
                encoding="utf-8",
            )
        else:
            # 纯框架文件，直接替换
            target_path.write_text(fw_content, encoding="utf-8")
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(fw_content, encoding="utf-8")

    changes = 1
    if gotchas_content:
        changes += 1
    return MigrateResult(
        "applied",
        f"生成合并版 CLAUDE.md" + (f"（保留自定义坑点）" if gotchas_content else ""),
        changes,
    )


# ============================================================
# Step 17: v3.0 create_context_snapshot
# ============================================================

def migrate_create_context_snapshot(ctx: UpgradeContext) -> MigrateResult:
    """创建初始 context-snapshot.md。"""
    snapshot_path = ctx.dev_state / "context-snapshot.md"

    if snapshot_path.exists():
        return MigrateResult("skipped", "context-snapshot.md 已存在")

    if ctx.dry_run:
        return MigrateResult("skipped", "[dry-run] 将创建 context-snapshot.md")

    # 从 session-state.json 读取当前状态
    state = load_session_state(ctx.project_dir)
    mode = "interactive"
    iteration = "iter-0"
    phase = "phase_0"
    completed = 0
    total = 0

    if state:
        mode = state.get("mode", "interactive")
        iteration = state.get("current_iteration", "iter-0")
        phase = state.get("current_phase", "phase_0")
        progress = state.get("progress", {})
        completed = progress.get("completed", 0)
        total = progress.get("total_tasks", 0)

    now = datetime.now(timezone.utc).isoformat()

    # 优先使用模板文件
    framework_dir = get_framework_dir()
    snapshot_tmpl = framework_dir / "templates" / "project" / "context-snapshot.md.tmpl"
    if snapshot_tmpl.exists():
        content = snapshot_tmpl.read_text(encoding="utf-8")
        replacements = {
            "{{TIMESTAMP}}": now,
            "{{MODE}}": mode,
            "{{ITERATION}}": iteration,
            "{{PHASE}}": phase,
            "{{TASK_ID}}": "无",
            "{{STATUS}}": "N/A",
            "{{CURRENT_STEP}}": "N/A",
            "{{TOOLCHAIN}}": "auto",
            "{{ITERATION_MODE}}": "standard",
            "{{TOTAL}}": str(total),
            "{{COMPLETED}}": str(completed),
            "{{IN_PROGRESS}}": "0",
            "{{PENDING}}": str(total - completed),
            "{{COMPLETED_LIST}}": "无" if completed == 0 else "（详见 tasks/）",
            "{{IN_PROGRESS_DETAIL}}": "无",
            "{{PENDING_LIST}}": "无" if total == 0 else "（详见 tasks/）",
            "{{DEPENDENCIES}}": "无",
            "{{TECH_DECISIONS}}": "从 v2.6 升级到 v3.0，初始快照",
            "{{FOUND_ISSUES}}": "无",
            "{{TECH_DETAILS}}": "无",
            "{{L1_PASSED}}": "0",
            "{{L1_FAILED}}": "0",
            "{{L2_PASSED}}": "0",
            "{{PENDING_VERIFY_LIST}}": "无",
            "{{REWORK_TASKS}}": "无",
            "{{NEXT_ACTION_1}}": "确认升级完成",
            "{{NEXT_ACTION_2}}": "启动 Claude Code 继续开发",
            "{{NEXT_ACTION_3}}": "按需开始新迭代",
        }
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)
    else:
        # fallback: 内联生成
        content = (
            f"# 当前上下文快照\n"
            f"> 最后更新: {now}\n\n"
            f"## 状态\n"
            f"- 模式: {mode} | 迭代: {iteration} | 阶段: {phase}\n"
            f"- 当前任务: 无\n"
            f"- 运行配置: toolchain=auto, iteration_mode=standard\n\n"
            f"## 进度总览\n"
            f"- 总计: {total} CR | 完成: {completed} | 进行中: 0 | 待开始: {total - completed}\n\n"
            f"## 关键上下文\n"
            f"- 从 v2.6 升级到 v3.0，初始快照\n\n"
            f"## 下一步\n"
            f"1. 确认升级完成\n"
            f"2. 启动 Claude Code 继续开发\n"
        )
    snapshot_path.write_text(content, encoding="utf-8")
    return MigrateResult("applied", "创建 context-snapshot.md", 1)


# ============================================================
# Step 18: v3.0 update_run_config_snapshot
# ============================================================

def migrate_update_run_config_snapshot(ctx: UpgradeContext) -> MigrateResult:
    """在 run-config.yaml 中添加 snapshot 配置块。"""
    rc_path = ctx.dev_state / "run-config.yaml"
    if not rc_path.exists():
        return MigrateResult("skipped", "run-config.yaml 不存在")

    content = rc_path.read_text(encoding="utf-8")

    if "snapshot:" in content:
        return MigrateResult("skipped", "run-config.yaml 已包含 snapshot 配置")

    if ctx.dry_run:
        return MigrateResult("skipped", "[dry-run] 将添加 snapshot 配置块")

    snapshot_block = (
        "\n# ──────────────────────────────────────────────────\n"
        "# 上下文快照配置（v3.0 新增）\n"
        "# ──────────────────────────────────────────────────\n"
        "snapshot:\n"
        "  # 是否启用滚动快照\n"
        "  enabled: true\n"
        "  # 更新频率: per_step(每个 CR step 后) | per_task(每个 CR 完成后)\n"
        '  update_frequency: "per_step"\n'
    )

    content = content.rstrip() + "\n" + snapshot_block
    rc_path.write_text(content, encoding="utf-8")
    return MigrateResult("applied", "添加 snapshot 配置块", 1)


# ============================================================
# Step 19: v3.0 update_gitignore_v3
# ============================================================

def migrate_update_gitignore_v3(ctx: UpgradeContext) -> MigrateResult:
    """在 .gitignore 中添加 context-snapshot.md。"""
    gitignore = ctx.project_dir / ".gitignore"

    if not gitignore.exists():
        if ctx.dry_run:
            return MigrateResult("skipped", "[dry-run] .gitignore 不存在")
        # 创建带有规则的 .gitignore
        gitignore.write_text("**/context-snapshot.md\n", encoding="utf-8")
        return MigrateResult("applied", "创建 .gitignore 并添加 context-snapshot.md", 1)

    content = gitignore.read_text(encoding="utf-8")
    if "context-snapshot.md" in content:
        return MigrateResult("skipped", ".gitignore 已包含 context-snapshot.md 规则")

    if ctx.dry_run:
        return MigrateResult("skipped", "[dry-run] 将添加 context-snapshot.md 到 .gitignore")

    # 在框架规则块中添加
    marker_end = "# === dev-framework: 自动生成规则结束 ==="
    if marker_end in content:
        content = content.replace(
            marker_end,
            "**/context-snapshot.md\n\n" + marker_end,
        )
    else:
        content = content.rstrip() + "\n**/context-snapshot.md\n"

    gitignore.write_text(content, encoding="utf-8")
    return MigrateResult("applied", "添加 context-snapshot.md 到 .gitignore", 1)


# ============================================================
# Step 20: write_version_marker_v3
# ============================================================

def migrate_write_version_marker_v3(ctx: UpgradeContext) -> MigrateResult:
    """写入 .framework-version = "3.0"。"""
    version_file = ctx.dev_state / ".framework-version"

    if version_file.exists():
        existing = version_file.read_text(encoding="utf-8").strip()
        if existing == TARGET_VERSION and not ctx.force:
            return MigrateResult("skipped", f"版本标记已是 {TARGET_VERSION}")

    if ctx.dry_run:
        return MigrateResult("skipped", f"[dry-run] 将写入 .framework-version = {TARGET_VERSION}")

    version_file.write_text(TARGET_VERSION + "\n", encoding="utf-8")
    return MigrateResult("applied", f"写入 .framework-version = {TARGET_VERSION}", 1)


# ============================================================
# Step 21: create_agents_dir (v4.0)
# ============================================================

def migrate_create_agents_dir(ctx: UpgradeContext) -> MigrateResult:
    """v4.0: 创建 .claude/agents/ 目录并注入子代理定义文件。"""
    agents_dir = ctx.project_dir / ".claude" / "agents"
    framework_dir = get_framework_dir()
    agents_src = framework_dir / "templates" / "agents"

    if not agents_src.exists():
        return MigrateResult("error", f"子代理模板目录不存在: {agents_src}")

    agent_files = ["analyst.md", "developer.md", "verifier.md", "reviewer.md", "verify-reviewer.md"]

    # 备份已有的 agents 目录
    if agents_dir.exists() and not ctx.dry_run:
        if ctx.backup_dir:
            backup_agents = ctx.backup_dir / "agents"
            shutil.copytree(agents_dir, backup_agents)
            _log(ctx, f"已备份 .claude/agents/ → {backup_agents}")

    if not ctx.dry_run:
        agents_dir.mkdir(parents=True, exist_ok=True)

    # 读取工具链配置用于模板变量替换
    config = load_run_config(ctx.project_dir)
    toolchain = detect_toolchain(ctx.project_dir, config)

    _shared_rules_path = agents_src / "_shared-rules.md"
    _shared_rules = "\n" + _shared_rules_path.read_text(encoding="utf-8") if _shared_rules_path.exists() else ""
    copied = 0
    for fname in agent_files:
        src = agents_src / fname
        dst = agents_dir / fname
        if not src.exists():
            _log(ctx, f"跳过: {fname}（模板不存在）")
            continue
        if not ctx.dry_run:
            content = src.read_text(encoding="utf-8")
            content = content.replace("{{FRAMEWORK_PATH}}", str(framework_dir))
            content = content.replace("{{TEST_RUNNER}}", toolchain["test_runner"])
            content = content.replace("{{PYTHON}}", toolchain["python"])
            content += _shared_rules
            dst.write_text(content, encoding="utf-8")
        copied += 1
        _log(ctx, f"注入: .claude/agents/{fname}")

    return MigrateResult("applied", f"注入 {copied} 个子代理定义文件", copied)


# ============================================================
# Step 22: regenerate_claude_md_v4 (v4.0)
# ============================================================

def migrate_regenerate_claude_md_v4(ctx: UpgradeContext) -> MigrateResult:
    """v4.0: 使用精简版模板重新生成 .claude/CLAUDE.md（仅 Leader 协议 + 子代理索引）。"""
    framework_dir = get_framework_dir()
    fw_tmpl = framework_dir / "templates" / "project" / "CLAUDE-framework.md.tmpl"
    claude_md = ctx.project_dir / ".claude" / "CLAUDE.md"

    if not fw_tmpl.exists():
        return MigrateResult("error", f"v4.0 模板不存在: {fw_tmpl}")

    if not claude_md.exists():
        return MigrateResult("skipped", ".claude/CLAUDE.md 不存在，跳过")

    # 提取现有的项目坑点内容
    existing_content = claude_md.read_text(encoding="utf-8")
    gotchas = ""

    # 尝试从 v3.0 格式提取（"十一、已知坑点" 或 "八、已知坑点"）
    for marker in ["## 十一、已知坑点与最佳实践", "## 八、已知坑点与最佳实践"]:
        if marker in existing_content:
            start = existing_content.index(marker) + len(marker)
            # 找到下一个 ## 标题或文件结尾
            rest = existing_content[start:]
            end_markers = ["\n## 十二、", "\n## 九、", "\n## 十、"]
            end = len(rest)
            for em in end_markers:
                if em in rest:
                    end = min(end, rest.index(em))
            gotchas_raw = rest[:end].strip()
            # 跳过注释行
            gotchas_lines = [
                l for l in gotchas_raw.split("\n")
                if not l.strip().startswith("<!--") and not l.strip().endswith("-->")
            ]
            gotchas = "\n".join(gotchas_lines).strip()
            break

    if not gotchas:
        gotchas = "<!-- 开发过程中发现的坑点和最佳实践，由 developer 子代理自动维护 -->"

    # 提取项目特有部分（非框架部分，如果存在 CLAUDE.md.tmpl 生成的内容）
    project_part = ""
    # 查找分隔线标记
    if "\n---\n\n# Dev-Framework 运行时手册" in existing_content:
        project_part = existing_content[:existing_content.index("\n---\n\n# Dev-Framework 运行时手册")]
    elif "# Dev-Framework 运行时手册" in existing_content and not existing_content.startswith("# Dev-Framework 运行时手册"):
        project_part = existing_content[:existing_content.index("# Dev-Framework 运行时手册")].rstrip("\n- ")

    if not ctx.dry_run:
        fw_content = fw_tmpl.read_text(encoding="utf-8")
        fw_content = fw_content.replace("{{FRAMEWORK_PATH}}", str(framework_dir))
        fw_content = fw_content.replace("{{PROJECT_GOTCHAS}}", gotchas)

        config = load_run_config(ctx.project_dir)
        toolchain = detect_toolchain(ctx.project_dir, config)
        fw_content = fw_content.replace("{{TEST_RUNNER}}", toolchain["test_runner"])
        fw_content = fw_content.replace("{{PYTHON}}", toolchain["python"])

        if project_part:
            final_content = project_part + "\n\n---\n\n" + fw_content
        else:
            final_content = fw_content

        claude_md.write_text(final_content, encoding="utf-8")

    return MigrateResult("applied", "重新生成 .claude/CLAUDE.md（v4.0 精简版）")


# ============================================================
# Step 23: update_gitignore_v4 (v4.0)
# ============================================================

def migrate_update_gitignore_v4(ctx: UpgradeContext) -> MigrateResult:
    """v4.0: 更新 .gitignore 注释（agents/ 目录说明）。"""
    gitignore = ctx.project_dir / ".gitignore"
    if not gitignore.exists():
        return MigrateResult("skipped", ".gitignore 不存在")

    content = gitignore.read_text(encoding="utf-8")

    # 更新注释：v3.0 → v4.0
    old_comment = "v3.0 Agent 协议已合并到 CLAUDE.md"
    new_comment = "v4.0 子代理协议位于 .claude/agents/"
    if old_comment in content:
        if not ctx.dry_run:
            content = content.replace(old_comment, new_comment)
            gitignore.write_text(content, encoding="utf-8")
        return MigrateResult("applied", "更新 .gitignore 注释为 v4.0")

    return MigrateResult("skipped", ".gitignore 中无 v3.0 注释标记")


# ============================================================
# Step 24: update_init_project_comment (v4.0)
# ============================================================

def migrate_update_init_project_comment(ctx: UpgradeContext) -> MigrateResult:
    """v4.0: 更新 session-state.json 中的 agents 字段说明。"""
    state_path = ctx.dev_state / "session-state.json"
    if not state_path.exists():
        return MigrateResult("skipped", "session-state.json 不存在")

    # session-state.json 结构不变，无需修改
    return MigrateResult("skipped", "session-state.json 结构不变")


# ============================================================
# Step 25: write_version_marker_v4 (v4.0)
# ============================================================

def migrate_write_version_marker_v4(ctx: UpgradeContext) -> MigrateResult:
    """v4.0: 写入版本标记 .framework-version = '4.0'。"""
    version_file = ctx.dev_state / ".framework-version"
    if not ctx.dry_run:
        version_file.write_text("4.0\n", encoding="utf-8")
    return MigrateResult("applied", "版本标记更新为 4.0")


# ============================================================
# 主流程
# ============================================================

# 迁移步骤定义（name, label, function）
MIGRATE_STEPS = [
    ("preflight_check",         "环境预检",                     migrate_preflight_check),
    ("detect_current_version",  "版本检测",                     migrate_detect_current_version),
    ("create_backup",           "文件备份",                     migrate_create_backup),
    ("rename_iteration_dirs",   "BC-1: 重命名 iteration->iter", migrate_rename_iteration_dirs),
    ("session_state_fields",    "补齐 session-state 字段",      migrate_session_state_fields),
    ("baseline_fields",         "补齐 baseline 字段",           migrate_baseline_fields),
    ("run_config",              "补齐 run-config 配置块",       migrate_run_config),
    ("acceptance_criteria",     "BC-5: acceptance_criteria 格式", migrate_acceptance_criteria),
    ("add_priority",            "BC-6: 添加 priority 字段",     migrate_add_priority),
    ("review_issues",           "BC-9: review_issues 格式",     migrate_review_issues),
    ("claude_md",               "[v2.6→v3.0] CLAUDE.md 章节合并（pre-v3.0 项目）", migrate_claude_md),
    ("experience_log",          "BC-3: experience-log 迁移",    migrate_experience_log),
    # 注：此步骤在 v2.6 中是"复制 Agent 文件"，v3.0 中改为"清理旧 agents/ 目录"
    ("agent_protocols",         "v3.0: 清理旧 agents/ 目录",    migrate_agent_protocols),
    ("git_hooks",               "BC-10: Git hooks 重新生成",    migrate_git_hooks),
    ("gitignore",               ".gitignore 追加",              migrate_gitignore),
    # v3.0 新增迁移步骤
    ("generate_merged_claude_md", "v3.0: 生成合并版 CLAUDE.md", migrate_generate_merged_claude_md),
    ("create_context_snapshot",   "v3.0: 创建 context-snapshot", migrate_create_context_snapshot),
    ("update_run_config_snapshot","v3.0: 添加 snapshot 配置",    migrate_update_run_config_snapshot),
    ("update_gitignore_v3",       "v3.0: .gitignore 更新",      migrate_update_gitignore_v3),
    ("write_version_marker_v3",   "写入 v3.0 版本标记",         migrate_write_version_marker_v3),
    # v4.0 新增迁移步骤
    ("create_agents_dir",         "v4.0: 创建 agents/ 目录",    migrate_create_agents_dir),
    ("regenerate_claude_md_v4",   "v4.0: 重新生成 CLAUDE.md",   migrate_regenerate_claude_md_v4),
    ("update_gitignore_v4",       "v4.0: .gitignore 注释更新",  migrate_update_gitignore_v4),
    ("update_init_project_comment","v4.0: session-state 检查",   migrate_update_init_project_comment),
    ("write_version_marker_v4",   "写入 v4.0 版本标记",         migrate_write_version_marker_v4),
]


def run_upgrade(ctx: UpgradeContext) -> bool:
    """执行全部迁移步骤，返回是否成功。"""
    print()
    if ctx.dry_run:
        print("=" * 60)
        print("  DRY RUN 模式 — 仅预览变更，不实际执行")
        print("=" * 60)
    print(f"  项目目录: {ctx.project_dir}")
    print(f"  状态目录: {ctx.dev_state}")
    print()

    has_error = False
    for i, (name, label, func) in enumerate(MIGRATE_STEPS, 1):
        prefix = f"[{i:2d}/{len(MIGRATE_STEPS)}]"
        try:
            result = func(ctx)
        except Exception as e:
            result = MigrateResult("error", str(e))

        ctx.results.append((label, result))

        # 状态图标
        icon = {"applied": "OK", "skipped": "--", "error": "!!"}.get(result.status, "??")
        print(f"  {prefix} [{icon}] {label}: {result.message}")

        if result.status == "error":
            has_error = True
            # preflight 失败则中止
            if name == "preflight_check":
                print("\n  环境预检失败，中止升级。")
                return False
            # detect_version 返回 skipped（已是目标版本）则中止
        if name == "detect_current_version" and result.status == "skipped":
            print(f"\n  已是 v{TARGET_VERSION}，无需升级。")
            return True

    # 输出汇总报告
    print()
    print("=" * 60)
    print("  升级报告")
    print("=" * 60)
    print()
    print(f"  {'步骤':<35} {'状态':<10} {'变更数':<6}")
    print(f"  {'-'*35} {'-'*10} {'-'*6}")
    for label, result in ctx.results:
        status_text = {"applied": "已应用", "skipped": "跳过", "error": "错误"}.get(result.status, result.status)
        print(f"  {label:<33} {status_text:<8} {result.changes:>4}")
    print()

    applied = sum(1 for _, r in ctx.results if r.status == "applied")
    skipped = sum(1 for _, r in ctx.results if r.status == "skipped")
    errors = sum(1 for _, r in ctx.results if r.status == "error")
    total_changes = sum(r.changes for _, r in ctx.results)

    print(f"  合计: {applied} 已应用, {skipped} 跳过, {errors} 错误, {total_changes} 项变更")

    if ctx.backup_dir:
        print(f"  备份: {ctx.backup_dir}")

    if not has_error:
        print(f"\n  升级完成! 当前版本: v{TARGET_VERSION}")
    else:
        print(f"\n  升级完成（有 {errors} 个错误，请检查）")

    print()
    return not has_error


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将已有项目升级到 dev-framework v4.0"
    )
    parser.add_argument(
        "--project-dir", required=True,
        help="目标项目目录路径",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅预览变更，不实际执行",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="跳过备份（不推荐）",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="强制重新执行已完成的步骤",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="输出详细日志",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(f"[ERROR] 项目目录不存在: {project_dir}")
        sys.exit(1)

    dev_state = project_dir / ".claude" / "dev-state"

    ctx = UpgradeContext(
        project_dir=project_dir,
        dev_state=dev_state,
        dry_run=args.dry_run,
        force=args.force,
        verbose=args.verbose,
        no_backup=args.no_backup,
    )

    success = run_upgrade(ctx)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
