#!/usr/bin/env python3
"""
init-project.py — 初始化新项目的开发框架 (v4.0)

用法:
    python dev-framework/scripts/init-project.py \
        --project-dir "<项目路径>" \
        --requirement-doc "<项目路径>/docs/requirements.md" \
        --tech-stack "python,react"

执行后在目标项目中生成:
    .claude/dev-state/      开发状态目录
    .claude/CLAUDE.md       项目宪法（需手动定制；v4.0 Leader 协议 + 子代理索引）
    .claude/agents/         子代理定义文件
    ARCHITECTURE.md         架构决策记录
    scripts/verify/         验收脚本目录
"""

import argparse
import json
import os
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── 框架内部导入 ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import detect_toolchain, load_run_config, get_framework_dir


def append_gitignore(project_dir: Path):
    """追加框架文件排除规则到 .gitignore（FIX-20）。"""
    gitignore = project_dir / ".gitignore"
    marker = "# === dev-framework: 以下由框架自动生成，禁止手动修改 ==="

    # 如果已有标记，跳过
    if gitignore.exists() and marker in gitignore.read_text(encoding="utf-8"):
        print("[INFO] .gitignore 已包含框架规则，跳过")
        return

    rules = f"""
{marker}
# 框架注入文件（脚本副本、配置；v4.0 子代理协议位于 .claude/agents/）
.claude/dev-state/

# 迭代记录（task YAML、verify 脚本、manifest）
# 这些文件由各端独立生成，双端开发时会产生冲突
.claude/dev-state/iter-*/
.claude/dev-state/iteration-*/

# 进度与状态文件
**/session-state.json
**/baseline.json
**/resume-summary.md
**/checkpoints/
**/ledger/

# 框架生成的临时文件
**/experience-log.md
**/run-config.yaml
**/context-snapshot.md

# === dev-framework: 自动生成规则结束 ===
"""

    with open(gitignore, "a", encoding="utf-8") as f:
        f.write(rules)
    print(f"  已追加框架 .gitignore 规则（{len(rules.splitlines())} 行）")


def _setup_git_hooks(project_dir: Path, toolchain: dict | None = None) -> None:
    """生成 Git hooks（pre-commit / commit-msg / pre-push）。

    v4.0: 拆分为 shell 入口 + Python 脚本两层结构。
    Shell 入口负责跨平台 Python 路径检测，Python 脚本为纯 Python 逻辑。
    Unicode 符号替换为 ASCII 以避免 GBK 终端 UnicodeEncodeError。
    """
    git_hooks_dir = project_dir / ".git" / "hooks"
    if not git_hooks_dir.exists():
        print(f"  跳过: Git hooks（.git/hooks/ 不存在，请先 git init）")
        return

    # 获取 Python 路径（优先使用 toolchain 检测结果）
    python_path = "python3"
    if toolchain and toolchain.get("python"):
        _py = toolchain["python"]
        # 如果是 "uv run python" 等复合命令，取第一个词作为回退，但 hook 入口
        # 需要直接调用 python 解释器，所以只用简单路径
        if " " not in _py:
            python_path = _py
        else:
            # 复合命令（如 "uv run python"）不适用于 shell 入口的 exec
            # 保持 python3 作为默认，让 shell 入口的 for 循环搜索
            python_path = "python3"

    def _make_shell_entry(hook_name: str) -> str:
        """生成 shell 入口脚本（所有 Hook 共用模板，仅 hook 名不同）。"""
        return (
            f"#!/bin/sh\n"
            f"# dev-framework hook — cross-platform Python detection\n"
            f'for cmd in "{python_path}" python3 python; do\n'
            f'    command -v "$cmd" >/dev/null 2>&1 && '
            f'exec "$cmd" "$(dirname "$0")/{hook_name}.py" "$@"\n'
            f"done\n"
            f'echo "[dev-framework] Python not found" >&2; exit 1\n'
        )

    # ── pre-commit.py ─────────────────────────────────────────
    pre_commit_py = '''\
#!/usr/bin/env python3
"""pre-commit hook: NotImplementedError + empty pass + Mock compliance check."""
import re, subprocess, sys

result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
changed = [f for f in result.stdout.strip().split("\\n") if f.endswith(".py") and f.strip()]
errors = []
warnings = []

for fp in changed:
    try:
        content = open(fp, encoding="utf-8").read()
    except (FileNotFoundError, OSError):
        continue
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if "NotImplementedError" in line and not stripped.startswith("#"):
            errors.append(f"{fp}:{i} -- NotImplementedError")
        if stripped == "pass" and i > 1:
            prev_lines = content.splitlines()[:i-1]
            if prev_lines:
                prev = prev_lines[-1].strip()
                if prev.endswith(":") and any(kw in prev for kw in ["def ", "class ", "elif ", "else", "if "]):
                    warnings.append(f"{fp}:{i} -- suspected empty pass")
    if fp.replace("\\\\", "/").startswith("tests/"):
        if re.search(r"\\b(mock|Mock|MagicMock|patch|mocker)\\b", content):
            if "MOCK-REASON:" not in content:
                errors.append(f"{fp} -- Mock missing # MOCK-REASON:")
            if "MOCK-REAL-TEST:" not in content:
                errors.append(f"{fp} -- Mock missing # MOCK-REAL-TEST:")
            expire_ok = "MOCK-EXPIRE-WHEN:" in content or "permanent:" in content
            if not expire_ok:
                errors.append(f"{fp} -- Mock missing # MOCK-EXPIRE-WHEN:")

if warnings:
    print("pre-commit warnings:")
    for w in warnings:
        print(f"  [WARN] {w}")

if errors:
    print("pre-commit check failed:")
    for e in errors:
        print(f"  [FAIL] {e}")
    sys.exit(1)
'''

    # ── commit-msg.py ─────────────────────────────────────────
    commit_msg_py = '''\
#!/usr/bin/env python3
"""commit-msg hook: validate format per run-config.yaml hooks.commit_message_pattern."""
import re, sys
from pathlib import Path

try:
    import yaml
    config_path = Path(".claude/dev-state/run-config.yaml")
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        pattern_mode = config.get("hooks", {}).get("commit_message_pattern", "default")
        custom_regex = config.get("hooks", {}).get("commit_message_regex", "")
    else:
        pattern_mode = "default"
        custom_regex = ""
except ImportError:
    pattern_mode = "default"
    custom_regex = ""

msg = open(sys.argv[1], encoding="utf-8").read().strip()
first_line = msg.split("\\n")[0]

if pattern_mode == "flexible":
    sys.exit(0)
elif pattern_mode == "cr-suffix":
    if not re.search(r"\\(CR-\\d{3,}\\)", first_line):
        print(f"commit message missing CR suffix: {first_line}")
        print(f"Required: free-form (CR-xxx)")
        sys.exit(1)
elif pattern_mode == "custom" and custom_regex:
    if not re.match(custom_regex, first_line):
        print(f"commit message does not match custom format: {first_line}")
        print(f"Regex: {custom_regex}")
        sys.exit(1)
else:  # default
    pattern = r"^\\[.+\\]\\s+\\S+[:\\uff1a].+\\(CR-\\d{3,}\\)$"
    if not re.match(pattern, first_line):
        print(f"commit message format mismatch: {first_line}")
        print(f"Required: [module] action: description (CR-xxx)")
        print(f"Example: [query] optimize: search cache hit rate (CR-003)")
        sys.exit(1)
'''

    # ── pre-push.py ───────────────────────────────────────────
    pre_push_py = '''\
#!/usr/bin/env python3
"""pre-push hook: run full L1 tests before push (toolchain-aware)."""
import shlex, subprocess, sys
from pathlib import Path

tests_dir = Path("tests")
if not tests_dir.exists():
    sys.exit(0)

test_cmd = None
try:
    import yaml
    config_path = Path(".claude/dev-state/run-config.yaml")
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        runner = config.get("toolchain", {}).get("test_runner", "auto")
        if runner != "auto":
            test_cmd = shlex.split(runner) + ["tests/", "-x", "-q", "--tb=line"]
except ImportError:
    pass

if test_cmd is None:
    if Path("uv.lock").exists():
        test_cmd = ["uv", "run", "pytest", "tests/", "-x", "-q", "--tb=line"]
    elif Path("poetry.lock").exists():
        test_cmd = ["poetry", "run", "pytest", "tests/", "-x", "-q", "--tb=line"]
    else:
        test_cmd = [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=line"]

result = subprocess.run(test_cmd, capture_output=True, text=True)
if result.returncode != 0:
    print("pre-push check failed: tests did not pass")
    print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
    sys.exit(1)
'''

    # ── 写入文件 ──────────────────────────────────────────────
    hooks = [
        ("pre-commit", pre_commit_py),
        ("commit-msg", commit_msg_py),
        ("pre-push", pre_push_py),
    ]

    for hook_name, py_content in hooks:
        # Shell 入口
        shell_path = git_hooks_dir / hook_name
        shell_path.write_text(_make_shell_entry(hook_name), encoding="utf-8")
        # Python 脚本
        py_path = git_hooks_dir / f"{hook_name}.py"
        py_path.write_text(py_content, encoding="utf-8")
        print(f"  生成: .git/hooks/{hook_name} + {hook_name}.py")

    # 设置 hooks 可执行权限（Unix/macOS）— 仅 shell 入口需要
    if os.name != "nt":
        for hook_name, _ in hooks:
            hook_path = git_hooks_dir / hook_name
            if hook_path.exists():
                hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
        print(f"  已设置 Git hooks 可执行权限")


def init_project(project_dir: Path, requirement_doc: str, tech_stack: str) -> None:
    """初始化新项目"""
    _toolchain = None
    framework_dir = get_framework_dir()
    project_dir = project_dir.resolve()
    now = datetime.now(timezone.utc)

    print(f"初始化项目: {project_dir}")
    print(f"需求文档: {requirement_doc}")
    print(f"技术栈: {tech_stack}")

    # 检查 requirement_doc 路径是否存在（WARN 级别，不阻断初始化）
    req_path = Path(requirement_doc)
    if not req_path.is_absolute():
        req_path = project_dir / req_path
    if not req_path.exists():
        print(f"  [WARN] 需求文档路径不存在: {requirement_doc}")
        print(f"         请在 Phase 1 开始前确保文档就绪")

    print()

    # 1. 创建目录结构
    dirs = [
        ".claude/dev-state/iter-0/tasks",
        ".claude/dev-state/iter-0/verify",
        ".claude/dev-state/iter-0/checkpoints",
        ".claude/agents",
        "scripts/verify",
        "tests/unit",
        "tests/integration",
        "config",
        "docs",
    ]

    for d in dirs:
        (project_dir / d).mkdir(parents=True, exist_ok=True)
        print(f"  创建目录: {d}")

    # 2. 生成 session-state.json（v4.0: agents/ 目录存放子代理定义文件）
    session_state = {
        "session_id": f"ses-{now.strftime('%Y%m%d-%H%M%S')}",
        "started_at": now.isoformat(),
        "last_updated": now.isoformat(),
        "mode": "interactive",
        "current_iteration": "iter-0",
        "current_phase": "phase_0",
        "current_task": None,
        "progress": {
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
        },
        "last_checkpoint": "",
        "consecutive_failures": 0,
        "agents": {"active": [], "idle": []},
    }
    state_path = project_dir / ".claude" / "dev-state" / "session-state.json"
    state_path.write_text(
        json.dumps(session_state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  生成: session-state.json")

    # 2.5 v3.0: 生成初始 context-snapshot.md
    snapshot_path = project_dir / ".claude" / "dev-state" / "context-snapshot.md"
    snapshot_tmpl = framework_dir / "templates" / "project" / "context-snapshot.md.tmpl"
    if snapshot_tmpl.exists():
        snapshot_content = snapshot_tmpl.read_text(encoding="utf-8")
        replacements = {
            "{{TIMESTAMP}}": now.isoformat(),
            "{{MODE}}": "interactive",
            "{{ITERATION}}": "iter-0",
            "{{PHASE}}": "phase_0",
            "{{TASK_ID}}": "无",
            "{{STATUS}}": "N/A",
            "{{CURRENT_STEP}}": "N/A",
            "{{TOOLCHAIN}}": "auto",
            "{{ITERATION_MODE}}": "standard",
            "{{TOTAL}}": "0",
            "{{COMPLETED}}": "0",
            "{{IN_PROGRESS}}": "0",
            "{{PENDING}}": "0",
            "{{COMPLETED_LIST}}": "无",
            "{{IN_PROGRESS_DETAIL}}": "无",
            "{{PENDING_LIST}}": "无",
            "{{DEPENDENCIES}}": "无",
            "{{TECH_DECISIONS}}": "项目刚初始化，尚无开发上下文",
            "{{FOUND_ISSUES}}": "无",
            "{{TECH_DETAILS}}": "无",
            "{{L1_PASSED}}": "0",
            "{{L1_FAILED}}": "0",
            "{{L2_PASSED}}": "0",
            "{{PENDING_VERIFY_LIST}}": "无",
            "{{REWORK_TASKS}}": "无",
            "{{NEXT_ACTION_1}}": "填写 .claude/CLAUDE.md 的占位符",
            "{{NEXT_ACTION_2}}": "准备需求文档",
            "{{NEXT_ACTION_3}}": "启动 Claude Code 开始 Phase 1",
        }
        for placeholder, value in replacements.items():
            snapshot_content = snapshot_content.replace(placeholder, value)
    else:
        # fallback: 内联生成
        snapshot_content = (
            f"# 当前上下文快照\n"
            f"> 最后更新: {now.isoformat()}\n\n"
            f"## 状态\n"
            f"- 模式: interactive | 迭代: iter-0 | 阶段: phase_0\n"
            f"- 当前任务: 无\n"
            f"- 运行配置: toolchain=auto, iteration_mode=standard\n\n"
            f"## 进度总览\n"
            f"- 总计: 0 CR | 完成: 0 | 进行中: 0 | 待开始: 0\n\n"
            f"## 关键上下文\n"
            f"- 项目刚初始化，尚无开发上下文\n\n"
            f"## 下一步\n"
            f"1. 填写 .claude/CLAUDE.md 的占位符\n"
            f"2. 准备需求文档\n"
            f"3. 启动 Claude Code 开始 Phase 1\n"
        )
    snapshot_path.write_text(snapshot_content, encoding="utf-8")
    print(f"  生成: context-snapshot.md")

    # 4. 生成 baseline.json（空基线）
    baseline = {
        "iteration": "iter-0",
        "timestamp": now.isoformat(),
        "git_commit": "",
        "test_results": {
            "l1_passed": 0,
            "l1_failed": 0,
            "l1_skipped": 0,
            "l2_passed": 0,
            "l2_failed": 0,
            "l2_skipped": 0,
        },
        "lint_clean": True,
        "pre_existing_failures": [],
    }
    baseline_path = project_dir / ".claude" / "dev-state" / "baseline.json"
    baseline_path.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  生成: baseline.json")

    # 5. 生成 run-config.yaml（优先从 templates/ 复制，回退到 schemas/）
    run_config_tmpl = framework_dir / "templates" / "project" / "run-config.yaml.tmpl"
    run_config_fallback = framework_dir / "schemas" / "run-config.yaml"
    run_config_dst = project_dir / ".claude" / "dev-state" / "run-config.yaml"
    if run_config_tmpl.exists():
        shutil.copy2(run_config_tmpl, run_config_dst)
        print(f"  生成: run-config.yaml (from templates/)")
    elif run_config_fallback.exists():
        # 加载 schema YAML 检查是否为嵌套格式（不可直接用作配置）
        import yaml as _yaml
        try:
            _schema = _yaml.safe_load(run_config_fallback.read_text(encoding="utf-8"))
            if isinstance(_schema, dict) and "fields" in _schema:
                print(f"  [ERROR] {run_config_fallback} 是 Schema 定义格式（含 fields 层级），"
                      f"不可直接用作项目配置。请确保 templates/project/run-config.yaml.tmpl 存在。")
            else:
                shutil.copy2(run_config_fallback, run_config_dst)
                print(f"  生成: run-config.yaml (from schemas/ fallback)")
        except Exception:
            shutil.copy2(run_config_fallback, run_config_dst)
            print(f"  生成: run-config.yaml (from schemas/ fallback)")
    else:
        print(f"  [WARN] run-config.yaml 模板不存在，跳过")

    # 6. 生成 manifest.json
    manifest = {
        "id": "iter-0",
        "mode": "init",
        "status": "active",
        "created_at": now.isoformat(),
        "requirement_doc": requirement_doc,
        "requirement_summary": requirement_doc.split("/")[-1] if "/" in requirement_doc else requirement_doc,
        "tech_stack": tech_stack.split(","),
        "phase": "phase_0",
        "last_checkpoint": "",
    }
    manifest_path = (
        project_dir / ".claude" / "dev-state" / "iter-0" / "manifest.json"
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  生成: iter-0/manifest.json")

    # 6.5 生成空白 feature-checklist.json（init-mode / iter-0 专用）
    checklist_path = project_dir / ".claude" / "dev-state" / "iter-0" / "feature-checklist.json"
    if not checklist_path.exists():
        checklist_content = {
            "description": "Feature checklist for init-mode (iter-0). analyst 子代理 fills in Phase 2, reviewer 子代理 updates in Phase 4.",
            "features": []
        }
        checklist_path.write_text(
            json.dumps(checklist_content, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  生成: iter-0/feature-checklist.json（空白，由 analyst 子代理在 Phase 2 填充）")

    # 7. 生成迭代初始文件
    empty_files = {
        ".claude/dev-state/iter-0/requirement-raw.md": f"# 原始需求\n\n需求文档路径: `{requirement_doc}`\n\n请参阅需求文档。\n",
        ".claude/dev-state/iter-0/decisions.md": "# 关键决策日志\n\n> 记录开发过程中的关键技术决策。\n\n---\n",
    }
    for rel_path, content in empty_files.items():
        file_path = project_dir / rel_path
        file_path.write_text(content, encoding="utf-8")
        print(f"  生成: {rel_path}")

    # 8. v3.0: 生成合并版 .claude/CLAUDE.md
    root_claude = project_dir / "CLAUDE.md"
    dot_claude = project_dir / ".claude" / "CLAUDE.md"

    if root_claude.exists():
        # 追加模式：已有项目
        print(f"  检测到已有 CLAUDE.md，采用追加模式 → .claude/CLAUDE.md")
        if not dot_claude.exists():
            # 生成框架运行时手册
            fw_tmpl = framework_dir / "templates" / "project" / "CLAUDE-framework.md.tmpl"
            if fw_tmpl.exists():
                fw_content = fw_tmpl.read_text(encoding="utf-8")
                fw_content = fw_content.replace("{{FRAMEWORK_PATH}}", str(framework_dir))
                fw_content = fw_content.replace("{{PROJECT_GOTCHAS}}", "<!-- 开发过程中发现的坑点和最佳实践，由 developer 子代理自动维护 -->")
                # 工具链命令替换
                run_config_path = project_dir / ".claude" / "dev-state" / "run-config.yaml"
                _config = load_run_config(project_dir) if run_config_path.exists() else {}
                _toolchain = detect_toolchain(project_dir, _config)
                fw_content = fw_content.replace("{{TEST_RUNNER}}", _toolchain["test_runner"])
                fw_content = fw_content.replace("{{PYTHON}}", _toolchain["python"])
                dot_claude.write_text(fw_content, encoding="utf-8")
                print(f"  生成: .claude/CLAUDE.md (v4.0 子代理架构版运行时手册，追加模式)")
            else:
                # 回退：简化版
                dot_claude.write_text(
                    f"# dev-framework 配置\n\n"
                    f"> 此文件由 dev-framework init-project.py 自动生成\n\n"
                    f"## 框架工作流\n"
                    f"- 框架路径: {framework_dir}\n"
                    f"- 质量门控：8 层 Gate（Gate 0-7）\n"
                    f"- 子代理角色：leader / analyst / developer / verifier / reviewer\n",
                    encoding="utf-8",
                )
                print(f"  生成: .claude/CLAUDE.md (简化版，追加模式)")
    elif not dot_claude.exists():
        # 全新项目：生成框架运行时手册 + 项目配置
        fw_tmpl = framework_dir / "templates" / "project" / "CLAUDE-framework.md.tmpl"
        proj_tmpl = framework_dir / "templates" / "project" / "CLAUDE.md.tmpl"

        parts = []

        # Part 1: 项目配置（从 CLAUDE.md.tmpl）
        if proj_tmpl.exists():
            proj_content = proj_tmpl.read_text(encoding="utf-8")
            proj_content = proj_content.replace("{{PROJECT_NAME}}", project_dir.name)
            proj_content = proj_content.replace("{{TECH_STACK}}", tech_stack)
            proj_content = proj_content.replace(
                "{{PROJECT_DESCRIPTION}}",
                f"<!-- TODO: 填写 {project_dir.name} 的一句话描述 -->",
            )
            proj_content = proj_content.replace(
                "{{PROJECT_OVERVIEW}}",
                f"<!-- TODO: 填写 {project_dir.name} 的项目概述 -->",
            )
            proj_content = proj_content.replace(
                "{{PROJECT_URL}}",
                "TODO: 填写项目仓库 URL",
            )
            proj_content = proj_content.replace(
                "{{PACKAGE_MANAGERS}}",
                "<!-- TODO: 填写包管理器说明（如 pip / uv / poetry / npm） -->",
            )
            proj_content = proj_content.replace(
                "{{CODE_STYLE}}",
                "<!-- TODO: 填写代码风格规范（如 ruff / black / eslint） -->",
            )
            proj_content = proj_content.replace(
                "{{DIRECTORY_STRUCTURE}}",
                "<!-- TODO: 填写关键目录结构 -->",
            )
            proj_content = proj_content.replace(
                "{{SECURITY_POLICY}}",
                "<!-- TODO: 填写安全策略（如密钥管理、输入校验规则） -->",
            )
            parts.append(proj_content)

        # Part 2: 框架运行时手册（从 CLAUDE-framework.md.tmpl）
        if fw_tmpl.exists():
            fw_content = fw_tmpl.read_text(encoding="utf-8")
            fw_content = fw_content.replace("{{FRAMEWORK_PATH}}", str(framework_dir))
            fw_content = fw_content.replace("{{PROJECT_GOTCHAS}}", "<!-- 开发过程中发现的坑点和最佳实践，由 developer 子代理自动维护 -->")
            # 工具链命令替换
            run_config_path = project_dir / ".claude" / "dev-state" / "run-config.yaml"
            _config = load_run_config(project_dir) if run_config_path.exists() else {}
            _toolchain = detect_toolchain(project_dir, _config)
            fw_content = fw_content.replace("{{TEST_RUNNER}}", _toolchain["test_runner"])
            fw_content = fw_content.replace("{{PYTHON}}", _toolchain["python"])
            parts.append(fw_content)

        if parts:
            dot_claude.write_text("\n\n---\n\n".join(parts), encoding="utf-8")
        else:
            dot_claude.write_text(
                f"# CLAUDE.md — {project_dir.name}\n\n"
                f"> 请基于 dev-framework 模板定制此文件。\n\n"
                f"技术栈: {tech_stack}\n"
                f"需求文档: {requirement_doc}\n",
                encoding="utf-8",
            )
        print(f"  生成: .claude/CLAUDE.md (v4.0 子代理架构版，需手动定制项目配置占位符)")

    # 9. v4.0: 写入版本标记
    version_path = project_dir / ".claude" / "dev-state" / ".framework-version"
    version_path.write_text("4.0\n", encoding="utf-8")
    print(f"  生成: .framework-version = 4.0")

    # 9.5 v4.0: 注入子代理定义文件到 .claude/agents/
    _agent_files = [
        "analyst.md",
        "developer.md",
        "verifier.md",
        "reviewer.md",
        "verify-reviewer.md",
    ]
    # 确保 _toolchain 可用（CLAUDE.md 生成阶段可能已检测过，但此处保底重新检测）
    if _toolchain is None:
        _run_cfg_path = project_dir / ".claude" / "dev-state" / "run-config.yaml"
        _cfg = load_run_config(project_dir) if _run_cfg_path.exists() else {}
        _toolchain = detect_toolchain(project_dir, _cfg)
    _shared_rules_path = framework_dir / "templates" / "agents" / "_shared-rules.md"
    _shared_rules = "\n" + _shared_rules_path.read_text(encoding="utf-8") if _shared_rules_path.exists() else ""
    for _agent_fn in _agent_files:
        _agent_src = framework_dir / "templates" / "agents" / _agent_fn
        if not _agent_src.exists():
            print(f"  [WARN] 子代理模板不存在，跳过: templates/agents/{_agent_fn}")
            continue
        _agent_content = _agent_src.read_text(encoding="utf-8")
        _agent_content = _agent_content.replace("{{FRAMEWORK_PATH}}", str(framework_dir))
        _agent_content = _agent_content.replace("{{TEST_RUNNER}}", _toolchain["test_runner"])
        _agent_content = _agent_content.replace("{{PYTHON}}", _toolchain["python"])
        _agent_content += _shared_rules
        _agent_dst = project_dir / ".claude" / "agents" / _agent_fn
        _agent_dst.write_text(_agent_content, encoding="utf-8")
        print(f"  生成: .claude/agents/{_agent_fn}")

    # 10. 生成 ARCHITECTURE.md
    arch_path = project_dir / "ARCHITECTURE.md"
    if not arch_path.exists():
        arch_src = framework_dir / "templates" / "project" / "ARCHITECTURE.md.tmpl"
        if arch_src.exists():
            content = arch_src.read_text(encoding="utf-8")
            content = content.replace("{{PROJECT_NAME}}", project_dir.name)
            arch_path.write_text(content, encoding="utf-8")
            print(f"  生成: ARCHITECTURE.md")
        else:
            print(f"  跳过: ARCHITECTURE.md（模板文件不存在: {arch_src}）")

    # 11. 生成 default.yaml
    config_path = project_dir / "config" / "default.yaml"
    if not config_path.exists():
        config_path.write_text(
            f"# {project_dir.name} 默认配置\n\n"
            f"# 本地覆盖请使用 config/local.yaml（不入 Git）\n",
            encoding="utf-8",
        )
        print(f"  生成: config/default.yaml")

    # 12. 生成 Git hooks（传入工具链以写入 Python 路径）
    _setup_git_hooks(project_dir, toolchain=_toolchain)

    # 13. 追加框架文件 .gitignore 规则（FIX-20）
    append_gitignore(project_dir)

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
