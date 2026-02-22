
---

## 共享规则（自动拼接，所有子代理通用）

### §1 测试层级定义

- **L0 验收测试**：零 Mock，真实环境运行，每个 CR 完成后运行
- **L1 单元测试**：仅白名单场景允许 Mock，commit 前必须通过
- **L2 集成测试**：零 Mock，完整链路，每批 CR 完成后运行

### §2 done_evidence 质量标准

done_evidence 必须包含三个字段（`tests`、`logs`、`notes`），缺任一项写入会被拒绝。

- **tests**：≥1 条摘要，格式为 `"CR-xxx verify: N/N PASS (时间戳)"`
- **logs**：≥N 条（N = acceptance_criteria 条数），必须与 acceptance_criteria **一一对应**
  - 每条格式：`"AC{n}: PASS/FAIL — {具体结果}"`
- **notes**：≥1 条结论性说明

Rework 后重新验收时，done_evidence **覆盖**旧版本（非追加），确保证据与最终代码一致。

### §3 EVIDENCE_JSON 输出/解析协议

verify 脚本通过 stdout 输出结构化证据，格式如下：

```
--- EVIDENCE_JSON ---
{ JSON 对象 }
--- END_EVIDENCE ---
```

- Verifier / Verify-Reviewer 运行 verify 脚本后，从 stdout 定位 `--- EVIDENCE_JSON ---` 与 `--- END_EVIDENCE ---` 标记，提取其间的 JSON 作为 done_evidence 初始数据
- 标记缺失时（旧版脚本或异常退出），手动从 stdout 构造 done_evidence

### §4 Mock 合规规则

**白名单**（仅以下 3 场景允许 Mock）：
1. 付费外部 API（需有对应的真实 API E2E 测试）
2. CI 环境无硬件
3. 不可控第三方服务

**三注解格式**（每个 Mock 必须同时声明）：
```python
# MOCK-REASON: {为什么需要 Mock}
# MOCK-REAL-TEST: {对应的真实测试路径::函数名}
# MOCK-EXPIRE-WHEN: {什么条件下此 Mock 应被移除} 或 permanent: {原因}
```

**审查步骤**：
1. `grep -r "MOCK-REASON\|MOCK-REAL-TEST\|MOCK-EXPIRE-WHEN" tests/` 扫描所有 Mock
2. 验证 `MOCK-REAL-TEST` 指向的测试文件和函数**真实存在**
3. 检查 Mock 场景是否在白名单内，不在白名单的 Mock 必须移除

### §5 回归判定公式

- 判定公式：`当前 l1_passed >= baseline.test_results.l1_passed`
- `pre_existing_failures` 中列出的测试不计为回归
- 任何不在 `pre_existing_failures` 中的新失败 = 回归
- 发现回归 → 立即标记 rework（Developer）或阻止 PASS（Verifier/Reviewer）
