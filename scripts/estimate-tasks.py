#!/usr/bin/env python3
"""
estimate-tasks.py — 动态任务拆分规模估算（Analyst 辅助工具）

用法:
    python dev-framework/scripts/estimate-tasks.py \
        --modules 3 --risk high --complexity moderate --mode iterate

    python dev-framework/scripts/estimate-tasks.py \
        --modules 5 --risk medium --complexity complex --mode init

输出为建议的 CR 数量范围，仅供 Analyst 参考，最终由 Analyst 根据八维度检查结果决定。
偏离建议范围 50% 以上时应在 decisions.md 中说明原因。
"""

import argparse
import json
import math

RISK_MULTIPLIER = {
    "low": 1.0,
    "medium": 1.5,
    "high": 2.0,
    "critical": 2.5,
}

COMPLEXITY_FACTOR = {
    "simple": 1,
    "moderate": 2,
    "complex": 3,
}

LINES_FACTOR = {
    "small": 0,    # < 200 行预估改动
    "medium": 2,   # 200-500 行
    "large": 5,    # 500-1500 行
    "xlarge": 10,  # > 1500 行
}

# init-mode 基础设施 CR 数量参考（参考 init-mode.md 的 INF-001~006 模式）
MAX_INFRA_CRS = 6


def estimate(
    modules: int,
    risk: str,
    complexity: str,
    mode: str,
    lines: str = "medium",
) -> dict:
    """
    估算建议的 CR 数量范围。

    参数:
        modules: 受影响模块数
        risk: 风险等级 (low/medium/high/critical)
        complexity: 需求复杂度 (simple/moderate/complex)
        mode: 运行模式 (init/iterate)
        lines: 预估代码改动规模 (small/medium/large/xlarge)

    返回:
        包含 range, base, adjusted, infra, lines_adj, note 的字典
    """
    base = modules * COMPLEXITY_FACTOR[complexity]
    adjusted = base * RISK_MULTIPLIER[risk]

    # 代码量调整
    lines_adj = LINES_FACTOR[lines]
    adjusted += lines_adj

    infra = 0
    if mode == "init":
        # 首次开发需要额外的基础设施 CR
        infra = min(modules, MAX_INFRA_CRS)
        adjusted += infra

    # 计算范围（±30%）
    low = max(2, math.floor(adjusted * 0.7))
    high = min(50, math.ceil(adjusted * 1.3))

    return {
        "range": f"{low}-{high}",
        "base_calculation": f"{modules} modules x {COMPLEXITY_FACTOR[complexity]} ({complexity}) = {base}",
        "risk_adjustment": f"x {RISK_MULTIPLIER[risk]} ({risk}) = {base * RISK_MULTIPLIER[risk]:.0f}",
        "lines_adjustment": f"+ {lines_adj} ({lines}, 代码量调整)" if lines_adj > 0 else "无",
        "infra_addition": f"+ {infra} (基础设施 CR)" if infra > 0 else "无",
        "adjusted_total": f"{adjusted:.0f}",
        "note": "仅供参考，最终由 Analyst 根据七路径审视结果决定",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="动态任务拆分规模估算（Analyst 辅助工具）"
    )
    parser.add_argument(
        "--modules",
        type=int,
        required=True,
        help="受影响的模块数量",
    )
    parser.add_argument(
        "--risk",
        choices=["low", "medium", "high", "critical"],
        required=True,
        help="风险等级",
    )
    parser.add_argument(
        "--complexity",
        choices=["simple", "moderate", "complex"],
        required=True,
        help="需求复杂度",
    )
    parser.add_argument(
        "--mode",
        choices=["init", "iterate"],
        required=True,
        help="运行模式",
    )
    parser.add_argument(
        "--lines",
        choices=["small", "medium", "large", "xlarge"],
        default="medium",
        help="预估总代码改动规模 (small:<200行, medium:200-500行, large:500-1500行, xlarge:>1500行)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出",
    )
    args = parser.parse_args()

    result = estimate(args.modules, args.risk, args.complexity, args.mode, args.lines)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*50}")
        print(f"任务拆分规模估算")
        print(f"{'='*50}")
        print(f"\n输入:")
        print(f"  模块数: {args.modules}")
        print(f"  风险等级: {args.risk}")
        print(f"  复杂度: {args.complexity}")
        print(f"  模式: {args.mode}")
        print(f"  代码量: {args.lines}")
        print(f"\n计算过程:")
        print(f"  基础计算: {result['base_calculation']}")
        print(f"  风险调整: {result['risk_adjustment']}")
        if result["lines_adjustment"] != "无":
            print(f"  代码量调整: {result['lines_adjustment']}")
        if result["infra_addition"] != "无":
            print(f"  基础设施: {result['infra_addition']}")
        print(f"  调整后总计: {result['adjusted_total']}")
        print(f"\n建议 CR 范围: {result['range']}")
        print(f"\n{result['note']}")


if __name__ == "__main__":
    main()
