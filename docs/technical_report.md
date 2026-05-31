# BioHermes 技术报告

# BioHermes v2.0: Judge→Select→Execute→Verify Data Agent

**参赛赛道**: 赛道二 — 智能进化·Agent 能力评测
**团队**: BioHermes Team
**日期**: 2026年5月
**架构**: Judge → Select → Execute → Verify 四层循环

---

## 1. 系统概述

BioHermes v2.0 是一个基于 MinerU 工具链的 Data Agent 数据智能体，采用创新的四层循环架构。与传统 Agent 不同，BioHermes 在执行前先**判断**任务特征，**选择**最优工具组合，**执行**后自动**验证**结果质量，验证不通过时回环重新判断。

### 核心创新

1. **Judge 判断层**: LLM 驱动的任务语义分析，输出任务类型、复杂度、文档特征、推荐工具、风险因素
2. **Select 选优层**: 根据判断结果动态选择 MinerU backend、启用 OCR/公式/表格、确定并发策略
3. **Execute 执行层**: PipelineContext 数据流传递，步骤间上下文共享
4. **Verify 验证层**: 格式→完整性→一致性三级校验，不通过回环到 Judge

### 架构对比

传统 Agent 流程: `用户指令 → 关键词匹配 → 固定工具调用 → 硬编码返回`

BioHermes 流程: `用户指令 → LLM Judge → 动态 Select → Context Execute → Auto Verify → (回环)`

---

## 2. 系统架构

```
┌──────────────────────────────────────────────────────┐
│                    API Layer                           │
│  FastAPI + SSE + REST + Docker                        │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│                Agent Core                              │
│  ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐         │
│  │ Judge │→│Select │→│Execute│→│Verify │→(loop)    │
│  └───┬───┘  └───┬───┘  └───┬───┘  └───┬───┘         │
│      │          │          │          │               │
│  ┌───▼──────────▼──────────▼──────────▼───┐         │
│  │           Recovery Manager              │         │
│  │     Retry → Degrade → Skip              │         │
│  └────────────────────────────────────────┘         │
│  ┌────────────────────────────────────────┐         │
│  │         PipelineContext (数据流)         │         │
│  │  files → parsed → tables → structures   │         │
│  └────────────────────────────────────────┘         │
│  ┌────────────────────────────────────────┐         │
│  │       Self-Improve (自学习)              │         │
│  │  跨会话指标累积 → Judge/Executor 优化    │         │
│  └────────────────────────────────────────┘         │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│                  Tool Layer                            │
│  MinerUParser | TableExtractor | StructureExtractor   │
│  DataCleaner | ReportGenerator                        │
│  (all inherit BaseTool, unified execute interface)    │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│                  External Services                     │
│  MinerU API (pipeline) | PyMuPDF (fallback) | LLM    │
└──────────────────────────────────────────────────────┘
```

---

## 3. 关键技术实现

### 3.1 Judge 判断层

LLM 分析用户任务，输出结构化判断:

- **任务类型**: parse / batch / extract / pipeline / report
- **复杂度**: simple / medium / complex
- **文档特征**: 格式、是否含表格/公式/多栏/扫描件
- **推荐工具**: 按优先级排序的工具列表
- **执行策略**: sequential / parallel / hybrid
- **风险因素**: 低质量文档、大文件、特殊格式
- **降级方案**: 预设恢复路径

LLM 不可用时自动降级为关键词匹配。

### 3.2 Verify 验证层

三级自动验证:

| 级别 | 检查内容 | 失败处理 |
|------|---------|---------|
| 格式 | 输出非空、格式正确 | 重试步骤 |
| 完整性 | 步骤完成率、表格行数 | 标记 warning |
| 一致性 | 数字合计 vs 明细、列数匹配 | 回环 Judge |

验证不通过时，将错误信息附加到任务描述，重新进入 Judge 循环（最多 2 次）。

### 3.3 PipelineContext 数据流

每个步骤通过 PipelineContext 共享数据:
- `files`: 发现的文件列表
- `parsed_results`: MinerU 解析结果
- `tables`: 提取的表格
- `structures`: 结构化信息
- `_step_outputs`: 步骤间传递的中间结果

工具通过 `context.get_output(step_index)` 获取前序步骤输出。

### 3.4 三级异常恢复

1. **重试** (最多 3 次): 指数退避重试失败步骤
2. **降级**: MinerU → PyMuPDF 本地解析
3. **跳过**: 非关键步骤 (data_clean, report_generate) 标记 skipped 继续

---

## 4. Demo 示例

### Demo 1: 复杂 PDF 学术论文解析
- Judge 判断: task_type=parse, features={is_multicolumn, has_formulas, has_tables}
- Select: mineru_parse → structure_extract → table_extract → report_generate

### Demo 2: 多步任务规划 (核心)
- Judge 判断: task_type=extract, complexity=complex
- Select: 4 步执行计划
- Verify: 格式 + 完整性 + 数字一致性三级校验

### Demo 3: 批量处理与异常恢复
- Judge: task_type=batch, strategy=parallel
- Recovery: 失败文档自动降级到 PyMuPDF

### Demo 4: 复杂表格与图表解析
- Verify: 数字合计 vs 明细一致性检查

### Demo 5: 端到端知识库 Pipeline
- Judge: task_type=pipeline, strategy=hybrid
- 6 步完整 pipeline: 摄入 → 解析 → 切片 → 表格 → 清洗 → 报告

---

## 5. 系统性能

| 指标 | 数值 |
|------|------|
| Judge 判断 | < 2s (LLM) / < 10ms (关键词) |
| 单文档解析 | 2-30s (取决于页数) |
| 批量并发 | 最大 3 并行 |
| 降级切换 | < 1s |
| API 响应 | < 100ms (任务提交) |

## 6. 部署

```bash
docker-compose up -d
# API: http://0.0.0.0:9091
```

## 7. Self-Improve 自学习机制

### 7.1 设计理念

传统 Agent 每次执行都是独立的，无法从历史中积累经验。BioHermes 的 Self-Improve 模块在每次 session 结束后提取执行指标，持久化到 JSON 文件，并在后续 session 的 Judge/Executor 决策中注入历史洞察。

### 7.2 学习维度

| 维度 | 数据结构 | 反馈目标 |
|------|---------|---------|
| 工具成功率 | `{tool_name: {task_type: ToolMetrics}}` | Judge 工具推荐排序 |
| Judge 准确度 | `{task_type: correct/total}` | Judge 风险提示 |
| 执行时长分布 | `total_duration / total_calls → avg × 3` | Executor 动态超时 |

### 7.3 反馈机制

- **Judge**: 历史成功率高的工具优先推荐；成功率低于 50% 的工具加入 risk_factors
- **Executor**: 用 `suggest_timeout(tool_name)` 替代固定 300s 超时，基于历史 avg × 3 估算 p95
- **冷启动安全**: 无历史数据时所有洞察返回空值，退化为默认策略

### 7.4 实现

```python
class SelfImprove:
    def learn(self, session: AgentSession, context: PipelineContext):
        # 提取: 工具成功率、Judge 准确度、执行时长
        # 持久化到 metrics.json

    def get_tool_insights(self, task_type: str) -> dict[str, float]:
        # 返回工具在指定任务类型下的成功率

    def suggest_timeout(self, tool_name: str, fallback: float = 300) -> float:
        # 基于历史 avg_duration × 3 建议超时
```

集成点：
- `core.py`: session 结束后调用 `self_improve.learn(session, context)`
- `judge.py`: 构造函数接收 self_improve，fallback 中调整工具排序
- `executor.py`: 每步执行前调用 `suggest_timeout()` 动态设置超时

## 8. 适用场景

- 学术论文批量解析与结构化
- 财务报表智能审核与数字一致性验证
- 工程文档处理与图表理解
- 法律文件结构化与关键信息抽取
- 知识库 Pipeline: 文档 → 结构化索引
