#!/usr/bin/env python3
"""
generate-report.py — 生成迭代报告

用法:
    python dev-framework/scripts/generate-report.py \
        --project-dir "D:/project" \
        --iteration-id "iter-3"
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


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
            except Exception:
                pass
    return tasks


def generate_report(project_dir: Path, iteration_id: str) -> None:
    """生成迭代报告"""
    project_dir = project_dir.resolve()
    dev_state = project_dir / ".claude" / "dev-state"

    # 加载数据
    tasks = load_tasks(project_dir, iteration_id)
    baseline_path = dev_state / "baseline.json"
    baseline = (
        json.loads(baseline_path.read_text())
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
    git_stat = subprocess.run(
        ["git", "diff", "--stat", f"HEAD~{total}"],
        capture_output=True, text=True, cwd=project_dir,
    )

    # 当前测试结果
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
        capture_output=True, text=True, cwd=project_dir, timeout=600,
    )

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
{git_stat.stdout.strip()[-500:]}
```

## 经验教训

"""

    # 读取 experience-log
    exp_log = dev_state / "experience-log.md"
    if exp_log.exists():
        content = exp_log.read_text(encoding="utf-8")
        # 取最后 20 行
        lines = content.strip().split("\n")[-20:]
        report += "\n".join(lines)
    else:
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
    generate_report(Path(args.project_dir), args.iteration_id)


if __name__ == "__main__":
    main()
