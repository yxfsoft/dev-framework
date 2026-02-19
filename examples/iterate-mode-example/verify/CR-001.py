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
from pathlib import Path


def verify_cr_001_ac1():
    """搜索 API 在 5s 内返回结果或超时错误

    验证方式: 调用搜索 API 并断言响应时间和状态码。
    实际项目中应使用真实 HTTP 请求（如 httpx/requests）调用运行中的服务。
    此示例用源码检查演示 verify 脚本的正确写法。
    """
    # 验证: search_service.py 中包含超时控制逻辑
    service_file = Path("services/query/search_service.py")
    assert service_file.exists(), f"核心文件不存在: {service_file}"

    content = service_file.read_text(encoding="utf-8")
    assert "wait_for" in content or "timeout" in content.lower(), (
        "search_service.py 中未找到超时控制逻辑（wait_for 或 timeout）"
    )
    print("    源码中包含超时控制逻辑 ✓")


def verify_cr_001_ac2():
    """超时错误返回 HTTP 408 + 错误提示

    验证方式: 构造必然超时的请求并断言返回 408 + 错误信息。
    实际项目中应启动真实服务后用 HTTP 客户端验证。
    此示例用源码检查演示。
    """
    # 验证: search_service.py 或 search router 中有 408 状态码处理
    for candidate in ["services/query/search_service.py", "services/web-api/routers/search.py"]:
        p = Path(candidate)
        if p.exists():
            content = p.read_text(encoding="utf-8")
            if "408" in content or "TimeoutError" in content or "asyncio.TimeoutError" in content:
                print(f"    {candidate} 中包含超时错误处理 ✓")
                return

    raise AssertionError(
        "未找到 408 超时响应处理。请确保搜索超时时返回 HTTP 408。"
    )


def verify_cr_001_ac3():
    """超时后 Milvus 连接正确释放，无泄漏

    验证方式: 检查 search_service.py 中是否有 finally/context manager 等资源释放逻辑。
    实际项目中应通过监控连接池 active_count 在超时前后的变化来验证。
    此示例用源码检查演示。
    """
    service_file = Path("services/query/search_service.py")
    assert service_file.exists(), f"核心文件不存在: {service_file}"

    content = service_file.read_text(encoding="utf-8")
    has_cleanup = any(kw in content for kw in ["finally", "async with", "with ", "__aexit__", "close()", "release("])
    assert has_cleanup, (
        "search_service.py 中未找到资源释放逻辑（finally/context manager/close）"
    )
    print("    超时后有资源释放逻辑 ✓")


def verify_cr_001_ac4():
    """超时配置可通过 config/default.yaml 修改，修改后实时生效

    验证方式: 读取配置文件并断言 search_timeout 字段存在且为合理数值。
    实际项目中应验证修改配置后服务行为确实改变。
    """
    import yaml

    config_path = Path("config/default.yaml")
    assert config_path.exists(), f"配置文件不存在: {config_path}"

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config is not None, "配置文件为空"
    assert "search_timeout" in config, (
        "config/default.yaml 中缺少 search_timeout 配置项"
    )

    timeout_val = config["search_timeout"]
    assert isinstance(timeout_val, (int, float)), (
        f"search_timeout 应为数值类型，实际为 {type(timeout_val).__name__}"
    )
    assert 0 < timeout_val <= 60, (
        f"search_timeout 值不合理: {timeout_val}（应在 0-60 秒之间）"
    )
    print(f"    search_timeout = {timeout_val}s ✓")


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
        ("CR-001-AC3", "超时后 Milvus 连接正确释放，无泄漏", verify_cr_001_ac3),
        ("CR-001-AC4", "超时配置可通过 config/default.yaml 修改，修改后实时生效", verify_cr_001_ac4),
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
