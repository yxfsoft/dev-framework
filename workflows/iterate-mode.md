# Iterate-Mode 工作流（迭代开发）

> 适用于：已有项目的 bug 修复、功能增强、新功能添加、重构
> 输入：变更需求 + 现有项目路径
> 输出：增量代码变更

---

## 概述

迭代开发在已有代码库上执行增量变更。
核心约束：**不破坏已有功能，改动范围可控。**

---

## Phase 0: 环境就绪

### Step 0.1: 代码同步

```bash
cd {project}
git pull --rebase origin main
```

### Step 0.2: 读取项目文档

- CLAUDE.md — 项目规范和技术栈
- ARCHITECTURE.md — 架构决策记录
- .claude/dev-state/experience-log.md — 已知坑点

### Step 0.3: 恢复上下文（如果是恢复的 session）

- 读 session-state.json
- 读最新 checkpoint
- 读 tasks/*.yaml
- 输出恢复摘要

### Step 0.4: 建立基线

```bash
# 运行全量测试
pytest tests/ -q --tb=no > baseline_output.txt

# 记录结果
python dev-framework/scripts/run-baseline.py \
    --project-dir "D:/my-project" \
    --iteration-id "iter-3"
```

基线内容：
```json
{
  "iteration": "iter-3",
  "timestamp": "2026-02-19T14:00:00",
  "test_results": {
    "l1_passed": 2381,
    "l1_failed": 0,
    "l2_passed": 102
  },
  "lint_clean": true
}
```

**如果基线本身有失败，记录并标注为"预存失败"，后续不计为回归。**

---

## Phase 1: 需求接收与深化

### Step 1.1: 接收需求

用户提供变更需求，可以是：
- 简短文字描述（"搜索太慢了"）
- 详细需求文档
- Issue/Bug 报告
- 功能增强请求

### Step 1.2: 需求交互确认

按 `workflows/requirement-intake.md` 执行。

### Step 1.3: 现状分析

Analyst 读取现有实现，理解当前行为：
- 读取相关源代码文件
- 读取相关测试文件
- 记录当前行为和问题

### Step 1.4: 需求深化

Analyst 按八维度检查，输出 requirement-spec.md。

### Step 1.5: 用户审批

Interactive 模式下等待用户审批。

---

## Phase 2: 影响分析 + 任务拆分

### Step 2.1: 影响分析

```markdown
# 影响分析

## 变更类型分类
- CR-001: bug_fix (搜索超时)
- CR-002: enhancement (搜索缓存)
- CR-003: new_feature (搜索过滤)

## 直接影响文件
- services/query/search_service.py (核心修改)
- services/web-api/routers/search.py (接口新增参数)
- packages/web-ui/src/hooks/useSearch.ts (前端适配)

## 间接影响
- tests/unit/test_search_service.py (测试更新)
- config/default.yaml (新增搜索配置段)

## 不受影响（明确排除）
- services/pipeline/* (入库逻辑不变)
- apps/windows/* (采集端不变)

## 风险点
- search_service.py 被 mcp/server.py 也调用，修改签名需同步
```

### Step 2.2: 任务拆分

按变更类型选择对应模板：

| 变更类型 | 模板 | 特殊要求 |
|---------|------|---------|
| bug_fix | bug-fix.yaml.tmpl | 必须有复现步骤 + 回归测试 |
| enhancement | enhancement.yaml.tmpl | 必须描述当前和期望行为 |
| new_feature | new-feature.yaml.tmpl | 必须有集成点说明 |
| refactor | refactor.yaml.tmpl | 必须列出不变量 |

### Step 2.3: 生成 verify 脚本

每个 CR 对应一个 verify 脚本：
- 零 Mock
- 使用真实环境
- 验证所有 acceptance_criteria

### Step 2.4: 用户审批

展示任务列表 + 影响分析 + 依赖关系。

---

## Phase 3: 开发执行

### Step 3.1: 团队组建

```
CR ≤ 3: Leader 兼任 Developer 和 Verifier，无需建团队
CR 4-8: 1 Leader + 1-2 Developer + 1 Verifier + 1 Reviewer
CR > 8: 1 Leader + 2-3 Developer + 1 Verifier + 1 Reviewer
```

### Step 3.2: 任务分配

```
1. 按依赖排序
2. 无依赖可并行（最多 3 Agent）
3. rework 任务优先
4. 每 Agent 同一时间只做一个 CR
```

### Step 3.3: 开发循环

每个 Developer 按 `agents/developer.md` 的工作流执行：

```
读代码 → 编码 → 编码自检 → L1 测试 → 基线回归 → commit → ready_for_verify
  → [Verifier 独立 L0 验收 + 证据收集] → ready_for_review
```

### Step 3.4: 集成检查点

每完成一批（2-3 个）CR 后：
1. 全量 L1 ≥ baseline
2. L2 集成测试通过
3. 受影响模块 E2E 验证
4. 无新增 TODO/FIXME/NotImplementedError
5. git diff --stat 确认范围

---

## Phase 4: 审查验收

### Step 4.1: 审查

Reviewer 按 `agents/reviewer.md` 审查每个 ready_for_review 的 CR。

### Step 4.2: 处理结果

- PASS → 标记完成
- REWORK → 通知 Developer，回到 Phase 3

### Step 4.3: 全量验收

所有 CR 为 PASS 后：
1. 运行全量 L1 + L2 测试
2. 结果 ≥ baseline
3. Lint 通过
4. 无新增 TODO/FIXME

---

## Phase 5: 交付

### Step 5.1: 生成迭代报告

```markdown
# 迭代报告: iter-3

## 概要
- 迭代时间: 2026-02-19
- CR 总数: 12
- 通过: 12, 失败: 0, 跳过: 0

## 变更汇总
| CR | 类型 | 标题 | 状态 |
|----|------|------|------|
| CR-001 | bug_fix | 搜索超时修复 | PASS |
| ... |

## 测试结果
- L1: 2412 passed (+31 new)
- L2: 108 passed (+6 new)
- 基线: 2381 → 2412 (+31)

## 代码统计
- 文件变更: 18
- 新增行: 1,245
- 删除行: 342

## 经验教训
- {从 experience-log.md 提取}

## 后续建议
- {下一轮迭代建议}
```

### Step 5.2: 更新状态文件

- manifest.json: status → completed
- session-state.json: 清除当前任务
- experience-log.md: 追加新经验

### Step 5.3: Git 提交

```bash
git add .claude/dev-state/
git commit -m "[dev-state] 完成: iter-3 迭代报告"
git push
```

---

## Iterate-Mode 特有规则

1. **基线保护**：测试结果永远不能低于 baseline.json
2. **改动范围**：每个 CR ≤ 5 个文件，超过则拆分
3. **预读义务**：修改 N 行代码前必须读至少 10N 行上下文
4. **回归优先**：发现回归立即停止新任务，优先修复
5. **不动无关代码**：只改需求涉及的代码，不做"顺手优化"
