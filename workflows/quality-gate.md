# 质量门控规则

> 适用于：所有模式（init-mode / iterate-mode）
> 执行者：见各 Gate 的"执行者"字段
> 目的：确保每个环节的产出质量达标
>
> **`<框架路径>` 说明**：指 dev-framework 仓库的根目录（即包含 `scripts/`、`agents/`、`workflows/` 的目录）。
> 可通过环境变量（如 `DEV_FRAMEWORK_DIR`）、绝对路径、或相对于项目目录的路径指定。

---

## Phase-Gate 映射表

| Phase | Gate | 说明 |
|-------|------|------|
| Phase 0 | Gate 0 | 环境就绪 |
| Phase 1 | Gate 1 | 需求完整 |
| Phase 2 | Gate 2 | 任务可执行 |
| Phase 3 | Gate 3 | 编码完成 |
| Phase 3.5 | Gate 4 | L1 回归通过 |
| Phase 4 | Gate 5 | 验收通过 |
| Phase 4 | Gate 6 | 评审通过 |
| Phase 5 | Gate 7 | 迭代完成 |

---

## 一、门控点总览

| Gate | 名称 | 检查内容 | 执行者 | 自动化状态 |
|------|------|---------|--------|-----------|
| Gate 0 | 环境就绪 | 开发环境可用 + 基线测试通过 | Leader Agent | 手动检查（phase-gate.py 自动放行 phase_0→1） |
| Gate 1 | 需求审批 | 需求规格书通过用户确认 | Leader Agent + 用户 | 手动检查（phase-gate.py 自动放行 phase_1→2） |
| Gate 2 | 任务拆分审批 | 任务列表 + verify 脚本通过确认 | Leader Agent + 用户 | **自动化**: `phase-gate.py --from phase_2 --to phase_3` |
| Gate 2.5 | 开发→验收 | 所有 CR 开发完成 | Leader Agent | **自动化**: `phase-gate.py --from phase_3 --to phase_3.5` |
| Gate 3 | L0 验收 | 每个 CR 的 verify 脚本全部 PASS | Verifier Agent | **自动化**: `check-quality-gate.py --gate gate_3` |
| Gate 3.5 | 验收→审查 | 所有 CR 验收通过 | Leader Agent | **自动化**: `phase-gate.py --from phase_3.5 --to phase_4` |
| Gate 4 | L1 回归 | 全量单元测试 ≥ 基线 | Verifier Agent | **自动化**: `check-quality-gate.py --gate gate_4` |
| Gate 5 | 集成检查点 | 每批 CR 完成后的集成验证 | Leader Agent | **半自动**: `check-quality-gate.py --gate gate_5`（部分检查需手动） |
| Gate 6 | 代码审查 | Reviewer 独立审查 PASS | Reviewer Agent | **自动化**: `check-quality-gate.py --gate gate_6` |
| Gate 7 | 最终验收 | 全量测试 + lint + E2E | Leader Agent + Reviewer Agent | **自动化**: `phase-gate.py --from phase_4 --to phase_5` |

---

## 一点五、质量检查脚本分工

框架提供两个质量检查脚本，职责不同：

| 脚本 | 职责 | 触发时机 | 用法示例 |
|------|------|---------|---------|
| `<框架路径>/scripts/phase-gate.py` | **Phase 转换门控**：检查从 Phase N 转换到 Phase N+1 的前置条件是否满足 | 每次 Phase 转换前 | `python <框架路径>/scripts/phase-gate.py --project-dir "." --iteration-id "iter-1" --from phase_2 --to phase_3` |
| `<框架路径>/scripts/check-quality-gate.py` | **任务级质量检查**：检查单个任务或单个 Gate 是否满足质量标准 | 任务状态变更时 | `python <框架路径>/scripts/check-quality-gate.py --project-dir "." --gate "gate_3" --iteration-id "iter-1" --task-id "CR-001"` |

**phase-gate.py 覆盖范围**：
- `phase_0→1` 和 `phase_1→2`：自动放行（无前置门控检查）
- `phase_2→3`：检查 tasks 目录非空、verify 脚本完整、脚本质量底线
- `phase_3→3.5`：检查所有 CR 状态为 ready_for_verify 或更后
- `phase_3.5→4`：检查所有 CR 状态为 ready_for_review 或 PASS
- `phase_4→5`：检查所有 CR 为 PASS、done_evidence 非空、review_result 非空

---

## 二、各门控详细规则

### Gate 0: 环境就绪

**触发时机**: Phase 0 完成时
**执行者**: Leader Agent（手动检查）
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
**执行者**: Leader Agent + 用户（interactive 模式下用户审批）
**检查内容**:
- [ ] requirement-spec.md 存在且完整（10 个章节）。Analyst 初稿可用 7 章快速输出，但提交 Gate 1 审批前必须补齐至 10 章
- [ ] 验收标准 ≥ 3 条
- [ ] 每条验收标准可机器验证
- [ ] 性能指标有量化值
- [ ] 用户已确认（interactive 模式）

**失败处理**: 返回需求深化环节

### Gate 2: 任务拆分审批

**触发时机**: Phase 2 完成时
**执行者**: Leader Agent + 用户（interactive 模式下用户审批）
**自动化**: `python <框架路径>/scripts/phase-gate.py --from phase_2 --to phase_3`
**检查内容**:
- [ ] 每个 CR 有完整的 design + acceptance_criteria
- [ ] 每个 CR 改动 ≤ 5 个文件
- [ ] 每个 CR 有对应的 verify 脚本
- [ ] verify 脚本零 Mock
- [ ] 依赖关系无循环
- [ ] 并行策略标注完整
- [ ] 用户已确认（interactive 模式）

**失败处理**: Analyst 调整拆分方案

### Gate 2.5: 开发完成（Phase 3 → Phase 3.5）

**触发时机**: Phase 3 开发全部完成后
**执行者**: Leader Agent
**自动化**: `python <框架路径>/scripts/phase-gate.py --from phase_3 --to phase_3.5`
**检查内容**:
- [ ] 所有 CR 状态为 `ready_for_verify` 或更后的状态
- [ ] 无 CR 处于 `pending` 或 `in_progress` 状态

**失败处理**: 继续 Phase 3 开发，直到所有 CR 完成

### Gate 3: L0 验收

**触发时机**: Developer 标记 ready_for_verify 后
**执行者**: Verifier Agent（独立于 Developer 执行）
**检查内容**:
- [ ] `python verify/CR-xxx.py` 全部 PASS
- [ ] 无 Mock 绕过
- [ ] done_evidence 已填写（tests、logs 非空）

**失败处理**: Verifier 标记 rework，Developer 修复后重新提交。超过 max_retries 标记 failed。

### Gate 3.5: 验收完成（Phase 3.5 → Phase 4）

**触发时机**: Phase 3.5 验收全部完成后
**执行者**: Leader Agent
**自动化**: `python <框架路径>/scripts/phase-gate.py --from phase_3.5 --to phase_4`
**检查内容**:
- [ ] 所有 CR 状态为 `ready_for_review` 或 `PASS`
- [ ] 无 CR 处于 `rework` 状态（需先修复再转换）

**失败处理**: 通知 Developer 修复 rework 的 CR，Verifier 重新验收

### Gate 4: L1 回归

**触发时机**: L0 通过后
**执行者**: Verifier Agent
**自动化**: `python <框架路径>/scripts/check-quality-gate.py --gate gate_4`
**检查内容**:
- [ ] `pytest tests/ -x -q` 全部通过
- [ ] passed 数 ≥ baseline.l1_passed
- [ ] failed 数 = 0（或 ≤ baseline.l1_failed，即预存失败）

**失败处理**:
- 新增失败 → Developer 修复
- 基线退化 → 立即停止，回退最后一次 commit

### Gate 5: 集成检查点

**触发时机**: 每完成一批（2-3 个）CR
**执行者**: Leader Agent
**自动化**: `python <框架路径>/scripts/check-quality-gate.py --gate gate_5`（部分检查需手动确认）
**检查内容**:
- [ ] Gate 4 通过（全量 L1）— **自动检查**（由 check-quality-gate.py 执行 lint/test）
- [ ] L2 集成测试通过（如果有）— **自动检查**（由脚本执行 pytest）
- [ ] 已修改文件中无新增 TODO/FIXME/NotImplementedError（跨平台检查方式见下方）— **自动检查**
- [ ] `git diff --stat` 范围符合预期 — **手动确认**（Leader/Reviewer 人工审核变更范围）
- [ ] 代码评审无阻塞问题 — **手动确认**（Reviewer 审查代码质量）
- [ ] 文档完整性（README、ARCHITECTURE.md 等已同步更新）— **手动确认**

**TODO/FIXME 跨平台检查方式**：
```bash
# Unix/macOS
grep -r "TODO\|FIXME\|NotImplementedError" {changed_files}

# Windows (PowerShell)
Select-String -Pattern "TODO|FIXME|NotImplementedError" -Path {changed_files}

# Windows (cmd)
findstr /s /i "TODO FIXME NotImplementedError" {changed_files}

# 推荐：使用 check-quality-gate.py 自动执行（内置跨平台支持）
python <框架路径>/scripts/check-quality-gate.py --project-dir "." --gate gate_5
```

**失败处理**: 停止新 CR 开发，优先修复

### Gate 6: 代码审查

**触发时机**: CR 标记为 ready_for_review（已通过 Verifier 验收）
**执行者**: Reviewer Agent（独立于 Developer 和 Verifier 执行）
**检查内容**: 见 `agents/reviewer.md` 审查清单（含维度 A-E）
**裁决规则**:
- 有 critical/high → REWORK
- 有 2+ medium → REWORK
- done_evidence 不完整 → REWORK
- 仅 low → PASS（记录建议）

**失败处理**: Developer 按 `review_result.issues` 修复，重新提交

### Gate 7: 最终验收

**触发时机**: 所有 CR 为 PASS
**执行者**: Leader Agent + Reviewer Agent（联合执行）
**自动化**: `python <框架路径>/scripts/phase-gate.py --from phase_4 --to phase_5`
**检查内容**:
- [ ] 全量 L1 测试通过
- [ ] 全量 L2 集成测试通过
- [ ] lint 通过
- [ ] 无新增 TODO/FIXME/NotImplementedError
- [ ] feature-checklist.json 全部 PASS（init-mode）
- [ ] 测试结果 ≥ baseline（iterate-mode）

**失败处理**: 回退到 Phase 3 修复

---

## 三、Mock 使用审查（v2.6 FIX-22 更新）

### 白名单（允许 Mock 的场景不变）

| 场景 | 条件 | 要求 |
|------|------|------|
| 付费外部 API | Claude/OpenAI 等 | 三项声明 + 对应真实 E2E 测试 |
| CI 无硬件 | GPU/麦克风/摄像头 | 三项声明 + 真机测试计划 |
| 不可控第三方 | Shizuku/Outlook COM | 三项声明 + 真机测试计划 |

### 黑名单（禁止 Mock）

| 场景 | 替代方案 |
|------|---------|
| 本地文件系统 | tmp_path 真实读写 |
| SQLite | :memory: 或临时文件 |
| 向量数据库 | 真实实例 + 测试 Collection |
| 自有 HTTP API | TestClient 真实启动 |
| 配置加载 | 临时配置文件 |

### Mock 三项声明（强制）

每个 Mock 必须同时包含以下三项注释，缺一不可：

| 声明 | 格式 | 用途 |
|------|------|------|
| `# MOCK-REASON:` | 自由文本 | 说明 Mock 存在的原因 |
| `# MOCK-REAL-TEST:` | `文件路径::函数名` | 指向对应的真实测试（必须存在） |
| `# MOCK-EXPIRE-WHEN:` | 条件描述 或 `permanent: 原因` | 定义 Mock 的移除条件 |

### Mock 生命周期

```
创建 Mock → 声明三项 → Reviewer 审查 → 通过
                                        ↓
                      每轮迭代 Phase 0 → Analyst 审查到期条件
                                        ↓
                      条件满足 → 创建 CR 移除 Mock
                      条件未满足 → 保留，下轮再审查
```

### 审查方式

Reviewer 在 Gate 6 中检查：
1. 搜索所有 Mock 使用点
2. 每个 Mock 是否在白名单中
3. 三项声明是否完整
4. `MOCK-REAL-TEST` 指向的文件是否存在
5. `MOCK-EXPIRE-WHEN` 的条件描述是否合理

---

## 四、Auto Loop 安全阀

| 条件 | 阈值 | 行为 |
|------|------|------|
| 连续任务失败 | max_consecutive_failures (默认 3) | 停止 + 诊断报告 |
| 基线退化 | 任何退化 | 立即停止 + 回退 |
| 单任务超时 | timeout_per_task (默认 30 分钟 / 1800 秒) | 标记 timeout + 跳过 |
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
