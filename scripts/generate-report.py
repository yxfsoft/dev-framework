#!/usr/bin/env python3
"""
generate-report.py — 生成迭代报告

用法:
    python dev-framework/scripts/generate-report.py \
        --project-dir "D:/project" \
        --iteration-id "iter-3"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加 scripts 目录到 path 以导入 fw_utils
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fw_utils import detect_toolchain, load_run_config, build_test_cmd

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML 未安装。运行: pip install PyYAML>=6.0")
    sys.exit(1)


def load_tasks(project_dir: Path, iteration_id: str) -> list[dict]:
    """加载所有任务"""
    tasks_dir = (
        project_dir / ".claude" / "dev-state" / iteration_id / "tasks"
    )
    tasks = []
    if tasks_dir.exists():
        for f in sorted(tasks_dir.glob("*.yaml")):
            try:
                content = f.read_text(encoding="utf-8")
                task = yaml.safe_load(content)
                if task:
                    tasks.append(task)
            except Exception as e:
                print(f"  WARN: 解析 {f} 失败: {e}", file=sys.stderr)
    return tasks


def generate_report(project_dir: Path, iteration_id: str) -> None:
    """生成迭代报告"""
    project_dir = project_dir.resolve()
    dev_state = project_dir / ".claude" / "dev-state"

    # 加载数据
    tasks = load_tasks(project_dir, iteration_id)
    baseline_path = dev_state / "baseline.json"
    baseline = (
        json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline_path.exists()
        else None
    )

    # 统计
    total = len(tasks)
    passed = sum(1 for t in tasks if t.get("status") == "PASS")
    failed = sum(1 for t in tasks if t.get("status") == "failed")
    rework = sum(1 for t in tasks if t.get("status") == "rework")
    pending = sum(1 for t in tasks if t.get("status") == "pending")

    # 首次通过率
    first_pass = sum(1 for t in tasks if t.get("status") == "PASS" and t.get("retries", 0) == 0)
    first_pass_rate = first_pass / total if total > 0 else 0

    # git 统计
    git_stat_output = ""
    if total > 0:
        # 获取实际提交数，避免 HEAD~N 超出历史范围
        commit_count_result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, cwd=project_dir,
            encoding="utf-8", errors="replace",
        )
        commit_count = 0
        if commit_count_result.returncode == 0:
            try:
                commit_count = int(commit_count_result.stdout.strip())
            except ValueError:
                commit_count = 0
        safe_n = min(total, max(commit_count - 1, 0))
        if safe_n > 0:
            git_diff_ref = f"HEAD~{safe_n}"
        else:
            # 只有一个或零个提交，使用空树作为对比基准
            git_diff_ref = "4b825dc642cb6eb9a060e54bf899d15f7acb7299"
        git_stat = subprocess.run(
            ["git", "diff", "--stat", git_diff_ref],
            capture_output=True, text=True, cwd=project_dir,
            encoding="utf-8", errors="replace",
        )
        git_stat_output = git_stat.stdout.strip()
    else:
        git_stat_output = "(无任务，跳过 diff)"

    # 当前测试结果（通过工具链配置检测）
    tests_dir = project_dir / "tests"
    if tests_dir.exists():
        config = load_run_config(project_dir)
        toolchain = detect_toolchain(project_dir, config)
        test_cmd = build_test_cmd(toolchain, "tests/", ["-q", "--tb=no"])
        test_result = subprocess.run(
            test_cmd,
            capture_output=True, text=True, cwd=project_dir, timeout=600,
            encoding="utf-8", errors="replace",
        )
    else:
        class _NoTestResult:
            stdout = "无测试目录 (tests/ 不存在)"
            stderr = ""
        test_result = _NoTestResult()

    # 生成报告
    report = f"""# 迭代报告: {iteration_id}

生成时间: {datetime.now(timezone.utc).isoformat()}

## 概要

| 指标 | 值 |
|------|-----|
| CR 总数 | {total} |
| 通过 | {passed} |
| 失败 | {failed} |
| 返工 | {rework} |
| 待做 | {pending} |
| 一次通过率 | {first_pass_rate:.1%} |

## 任务明细

| CR | 类型 | 标题 | 状态 | 重试 |
|----|------|------|------|------|
"""

    for t in tasks:
        tid = t.get("id", "?")
        ttype = t.get("type", "?")
        title = t.get("title", "?")
        status = t.get("status", "?")
        retries = t.get("retries", 0)
        report += f"| {tid} | {ttype} | {title} | {status} | {retries} |\n"

    report += f"""
## 测试结果

```
{test_result.stdout.strip()[-500:]}
```
"""

    if baseline:
        report += f"""
### 基线对比

| 指标 | 基线 | 当前 |
|------|------|------|
| L1 passed | {baseline['test_results']['l1_passed']} | (见上方) |
| L2 passed | {baseline['test_results']['l2_passed']} | (见上方) |
"""

    report += f"""
## 代码变更统计

```
{git_stat_output[-500:]}
```

## 经验教训

"""

    # 读取经验教训（v2.6: 优先从 CLAUDE.md 读取，回退到 experience-log.md）
    claude_md = project_dir / "CLAUDE.md"
    dot_claude_md = project_dir / ".claude" / "CLAUDE.md"
    exp_log = dev_state / "experience-log.md"

    exp_found = False
    for src in [claude_md, dot_claude_md]:
        if src.exists():
            content = src.read_text(encoding="utf-8")
            # 提取该章节（使用 find 替代 index 避免 ValueError）
            idx = content.find("已知坑点与最佳实践")
            if idx >= 0:
                section = content[idx:]
                lines = section.strip().split("\n")[:20]
                report += "\n".join(lines)
                exp_found = True
                break
    if not exp_found and exp_log.exists():
        content = exp_log.read_text(encoding="utf-8")
        lines = content.strip().split("\n")[-20:]
        report += "\n".join(lines)
    elif not exp_found:
        report += "(无记录)\n"

    # 写入报告
    report_path = (
        dev_state / iteration_id / f"report-{iteration_id}.md"
    )
    report_path.write_text(report, encoding="utf-8")

    print(f"迭代报告已生成: {report_path}")
    print()
    print(report[:1000])
    if len(report) > 1000:
        print(f"\n... (完整报告: {report_path})")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成迭代报告")
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument("--iteration-id", required=True, help="迭代 ID")
    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: --project-dir 目录不存在: {project_dir}")
        sys.exit(1)
    generate_report(project_dir, args.iteration_id)


if __name__ == "__main__":
    main()
