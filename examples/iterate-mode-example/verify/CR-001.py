#!/usr/bin/env python3
"""
CR-001 验收脚本
需求: 修复搜索 API 超时问题
生成时间: 2026-02-19T10:30:00+00:00

此脚本由 Analyst 生成。Developer 和 Verifier 不可修改。
零 Mock，使用真实环境验证。
"""

import json
import sys
import traceback
from datetime import datetime, timezone


def verify_cr_001_ac1():
    """搜索 API 在 5s 内返回结果或超时错误"""
    # 示例：实际项目中应调用真实的搜索 API
    # import httpx
    # resp = httpx.get("http://localhost:8000/api/search?q=test", timeout=6)
    # assert resp.status_code in (200, 408)
    # assert resp.elapsed.total_seconds() < 5.5
    print("    (示例脚本 — 实际项目中替换为真实验证逻辑)")


def verify_cr_001_ac2():
    """超时错误返回 HTTP 408 + 错误提示"""
    # 示例：构造一个必然超时的查询场景
    # resp = httpx.get("http://localhost:8000/api/search?q=*&timeout_ms=1", timeout=6)
    # assert resp.status_code == 408
    # body = resp.json()
    # assert "timeout" in body.get("error", "").lower()
    print("    (示例脚本 — 实际项目中替换为真实验证逻辑)")


def verify_cr_001_ac3():
    """超时配置可通过 config/default.yaml 修改"""
    # 示例：检查配置文件中存在 search_timeout 字段
    # import yaml
    # config = yaml.safe_load(open("config/default.yaml"))
    # assert "search_timeout" in config
    print("    (示例脚本 — 实际项目中替换为真实验证逻辑)")


def collect_evidence(results, task_id):
    """收集 done_evidence（供 Verifier 使用）"""
    timestamp = datetime.now(timezone.utc).isoformat()
    passed = sum(1 for _, s, _, _ in results if s == "PASS")
    total = len(results)
    return {
        "tests": [f"{task_id} verify: {passed}/{total} PASS ({timestamp})"],
        "logs": [f"{ac_id}: {status} - {desc}" for ac_id, status, desc, _ in results],
        "notes": ["全部通过" if passed == total else "存在失败项，需要修复"],
    }


def main():
    results = []
    criteria = [
        ("CR-001-AC1", "搜索 API 在 5s 内返回结果或超时错误", verify_cr_001_ac1),
        ("CR-001-AC2", "超时错误返回 HTTP 408 + 错误提示", verify_cr_001_ac2),
        ("CR-001-AC3", "超时配置可通过 config/default.yaml 修改", verify_cr_001_ac3),
    ]

    for ac_id, desc, fn in criteria:
        try:
            fn()
            results.append((ac_id, "PASS", desc, ""))
            print(f"  PASS  {ac_id}: {desc}")
        except AssertionError as e:
            results.append((ac_id, "FAIL", desc, str(e)))
            print(f"  FAIL  {ac_id}: {desc}")
            print(f"        原因: {e}")
        except NotImplementedError as e:
            results.append((ac_id, "ERROR", desc, str(e)))
            print(f"  ERROR {ac_id}: {desc}")
            print(f"        未实现: {e}")
        except Exception as e:
            results.append((ac_id, "ERROR", desc, traceback.format_exc()))
            print(f"  ERROR {ac_id}: {desc}")
            print(f"        异常: {e}")

    passed = sum(1 for _, s, _, _ in results if s == "PASS")
    total = len(results)
    print("\n" + "=" * 50)
    print(f"CR-001 验收结果: {passed}/{total} PASS")

    # 输出 done_evidence JSON（供 Verifier 解析）
    evidence = collect_evidence(results, "CR-001")
    print("\n--- EVIDENCE_JSON ---")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    print("--- END_EVIDENCE ---")

    if passed < total:
        sys.exit(1)
    else:
        print("\n全部通过!")
        sys.exit(0)


if __name__ == "__main__":
    main()
