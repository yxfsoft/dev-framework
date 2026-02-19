# 质量门控规则

> 适用于：所有模式（init-mode / iterate-mode）
> 执行者：Leader Agent + Reviewer Agent
> 目的：确保每个环节的产出质量达标

---

## 一、门控点总览

```
Gate 0: 环境就绪         → 开发环境可用 + 基线测试通过
Gate 1: 需求审批         → 需求规格书通过用户确认
Gate 2: 任务拆分审批     → 任务列表 + verify 脚本通过确认
Gate 3: L0 验收          → 每个 CR 的 verify 脚本全部 PASS
Gate 4: L1 回归          → 全量单元测试 ≥ 基线
Gate 5: 集成检查点       → 每批 CR 完成后的集成验证
Gate 6: 代码审查         → Reviewer 独立审查 PASS
Gate 7: 最终验收         → 全量测试 + lint + E2E
```

---

## 二、各门控详细规则

### Gate 0: 环境就绪

**触发时机**: Phase 0 完成时
**检查内容**:
- [ ] git status 工作区干净
- [ ] 开发语言/运行时版本正确
- [ ] 包管理器可用
- [ ] 依赖已安装
- [ ] 数据库/中间件可连接（如适用）
- [ ] 基线测试已运行且结果已记录（iterate-mode）

**失败处理**: 修复环境问题后重试

### Gate 1: 需求审批

**触发时机**: Phase 1 完成时
**检查内容**:
- [ ] requirement-spec.md 存在且完整（10 个章节）
- [ ] 验收标准 ≥ 3 条
- [ ] 每条验收标准可机器验证
- [ ] 性能指标有量化值
- [ ] 用户已确认（interactive 模式）

**失败处理**: 返回需求深化环节

### Gate 2: 任务拆分审批

**触发时机**: Phase 2 完成时
**检查内容**:
- [ ] 每个 CR 有完整的 design + acceptance_criteria
- [ ] 每个 CR 改动 ≤ 5 个文件
- [ ] 每个 CR 有对应的 verify 脚本
- [ ] verify 脚本零 Mock
- [ ] 依赖关系无循环
- [ ] 并行策略标注完整
- [ ] 用户已确认（interactive 模式）

**失败处理**: Analyst 调整拆分方案

### Gate 3: L0 验收

**触发时机**: Developer 标记 ready_for_verify 后
**执行者**: Verifier Agent（独立于 Developer 执行）
**检查内容**:
- [ ] `python verify/CR-xxx.py` 全部 PASS
- [ ] 无 Mock 绕过
- [ ] done_evidence 已填写（tests、logs 非空）

**失败处理**: Verifier 标记 rework，Developer 修复后重新提交。超过 max_retries 标记 failed。

### Gate 4: L1 回归

**触发时机**: L0 通过后
**检查内容**:
- [ ] `pytest tests/ -x -q` 全部通过
- [ ] passed 数 ≥ baseline.l1_passed
- [ ] failed 数 = 0（或 ≤ baseline.l1_failed，即预存失败）

**失败处理**:
- 新增失败 → Developer 修复
- 基线退化 → 立即停止，回退最后一次 commit

### Gate 5: 集成检查点

**触发时机**: 每完成一批（2-3 个）CR
**检查内容**:
- [ ] Gate 4 通过（全量 L1）
- [ ] L2 集成测试通过（如果有）
- [ ] `grep -r "TODO\|FIXME\|NotImplementedError" {changed_files}` 无结果
- [ ] `git diff --stat` 范围符合预期

**失败处理**: 停止新 CR 开发，优先修复

### Gate 6: 代码审查

**触发时机**: CR 标记为 ready_for_review（已通过 Verifier 验收）
**检查内容**: 见 `agents/reviewer.md` 审查清单（含维度 A-E）
**裁决规则**:
- 有 critical/high → REWORK
- 有 2+ medium → REWORK
- done_evidence 不完整 → REWORK
- 仅 low → PASS（记录建议）

**失败处理**: Developer 按 review_feedback 修复，重新提交

### Gate 7: 最终验收

**触发时机**: 所有 CR 为 PASS
**检查内容**:
- [ ] 全量 L1 测试通过
- [ ] 全量 L2 集成测试通过
- [ ] lint 通过
- [ ] 无新增 TODO/FIXME/NotImplementedError
- [ ] feature-checklist.json 全部 PASS（init-mode）
- [ ] 测试结果 ≥ baseline（iterate-mode）

**失败处理**: 回退到 Phase 3 修复

---

## 三、Mock 使用审查

### 白名单（允许 Mock）

| 场景 | 条件 | 要求 |
|------|------|------|
| 付费外部 API | Claude/OpenAI 等 | 声明理由 + 对应真实 E2E 测试 |
| CI 无硬件 | GPU/麦克风/摄像头 | 声明理由 + 真机测试计划 |
| 不可控第三方 | Shizuku/Outlook COM | 声明理由 + 真机测试计划 |

### 黑名单（禁止 Mock）

| 场景 | 替代方案 |
|------|---------|
| 本地文件系统 | tmp_path 真实读写 |
| SQLite | :memory: 或临时文件 |
| 向量数据库 | 真实实例 + 测试 Collection |
| 自有 HTTP API | TestClient 真实启动 |
| 配置加载 | 临时配置文件 |

### 审查方式

Reviewer 在 Gate 6 中检查所有测试文件：
```bash
# 搜索 Mock 使用
grep -r "mock\|Mock\|patch\|MagicMock" tests/
```
对每个 Mock 使用点，检查是否在白名单中且有声明理由。

---

## 四、Auto Loop 安全阀

| 条件 | 阈值 | 行为 |
|------|------|------|
| 连续任务失败 | max_consecutive_failures (默认 3) | 停止 + 诊断报告 |
| 基线退化 | 任何退化 | 立即停止 + 回退 |
| 单任务超时 | timeout_per_task (默认 1800s) | 标记 timeout + 跳过 |
| 总运行时间 | 无硬限制，但 checkpoint 保证可恢复 | — |
| git 冲突 | 任何冲突 | 停止 + 要求人工处理 |

### 诊断报告格式

```markdown
# Auto Loop 停止报告

## 停止原因
{连续失败 / 基线退化 / 超时}

## 状态快照
- 已完成: {x}/{y} CR
- 最后成功: CR-{n}
- 失败任务: CR-{m} (失败 {k} 次)

## 失败详情
- 任务: CR-{m}
- L0 verify 结果: {输出}
- L1 测试结果: {输出}
- 错误日志: {关键错误}

## 建议操作
1. {具体建议}
2. {具体建议}
```

---

## 五、质量指标追踪

每轮迭代完成后记录：

```json
{
  "iteration": "iter-3",
  "metrics": {
    "total_crs": 12,
    "passed_first_try": 10,
    "reworked": 2,
    "failed": 0,
    "first_pass_rate": 0.833,
    "test_delta": "+31",
    "files_changed": 18,
    "lines_added": 1245,
    "lines_deleted": 342
  }
}
```

追踪 first_pass_rate（一次通过率），用于评估开发质量趋势。
