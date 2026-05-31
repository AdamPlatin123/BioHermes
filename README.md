# BioHermes — MinerU Data Agent with Self-Validating Architecture

> **2026 MinerU 数据智能与前沿语料挑战赛 · 赛道二 — 智能进化·Agent 能力评测**

**BioHermes** 是一个基于 MinerU 工具链的数据智能体，采用原创的 **Judge → Select → Execute → Verify** 四层闭环架构。区别于业界主流 ReAct 和 LangGraph 方案，BioHermes 引入了任务前判断和结果后验证的双端智能，形成了"先想再做、做完自检"的完整认知闭环。

---

## 核心创新：为什么不是 ReAct / LangGraph？

当前赛道参赛方案主要采用 ReAct（推理-行动交替）或 LangGraph（有向图工作流）架构。BioHermes 选择了一条不同的路线：

| 维度 | ReAct 方案 | LangGraph 方案 | **BioHermes JSEV** |
|------|-----------|---------------|-------------------|
| 架构模式 | Thought→Action→Observation 循环 | 节点图 + 条件边 | **Judge→Select→Execute→Verify 四层闭环** |
| 任务理解 | 逐步推理，每次调用前分析 | 节点逻辑预定义 | **Judge 层迭代式语义分析，首轮判断 + 验证失败后携带错误上下文重新判断** |
| 工具选择 | LLM 即时决策 | 图节点硬编码 | **Select 层根据判断结果动态生成最优执行计划** |
| 结果验证 | 无或简单检查 | 无或简单检查 | **Verify 三级自动校验（格式→完整性→一致性），不通过回环重新判断** |
| 数据流 | 上下文窗口累积 | 节点间状态传递 | **PipelineContext 结构化数据流，步骤间显式传递** |
| 失败处理 | 重试或停止 | 节点异常处理 | **Recovery 三级恢复（重试→降级→跳过）+ Judge 回环** |
| 瓶颈风险 | LLM 调用频繁，token 消耗大 | 图结构固化，新任务需重新设计 | **LLM 集中在 Judge/Verify 高价值决策点，Execute 层不依赖 LLM** |

**关键差异**：BioHermes 将 LLM 集中部署在"判断"和"验证"两个高价值决策节点，而非每次工具调用都依赖 LLM 决策。这意味着：
- **LLM 用在关键决策点** → 判断质量和验证质量是系统天花板，值得投入最强模型
- **执行链路解耦 LLM** → 工具调用不受 LLM 输出波动影响，执行层稳定可靠
- **迭代式自我纠错** → Verify 不通过时携带错误上下文重新 Judge，形成认知闭环而非一次性猜测

---

## 架构详解

```
用户自然语言指令
       │
       ▼
  ┌─────────────┐
  │   Judge     │  ← LLM 语义分析: 任务类型 / 复杂度 / 文档特征 / 风险因素
  │   判断层     │     降级: 关键词匹配（LLM 不可用时自动切换）
  └──────┬──────┘
         │ JudgeResult: {task_type, complexity, features, tools[], strategy}
         ▼
  ┌─────────────┐
  │   Select    │  ← 根据判断结果选择:
  │   选优层     │     MinerU backend (pipeline/vlm)
  │             │     是否启用 OCR / 公式 / 表格
  │             │     并发策略 / 超时 / 重试策略
  │             │     输出: 有序 Step 序列，每步绑定 tool + args
  └──────┬──────┘
         │ execution_plan: [Step(tool, args, depends_on)]
         ▼
  ┌─────────────┐
  │   Execute   │  → 调用工具执行，PipelineContext 传递数据
  │   执行层     │     失败 → Recovery (重试 3 次 → PyMuPDF 降级 → 跳过)
  │             │     实时 SSE 推送进度
  └──────┬──────┘
         │ raw results
         ▼
  ┌─────────────┐
  │   Verify    │  ← 三级自动验证:
  │   验证层     │     Level 1 格式: 输出非空、格式正确
  │             │     Level 2 完整性: 步骤完成率、表格行列数
  │             │     Level 3 一致性: 数字合计 vs 明细、列数匹配
  │             │     不通过 → 回到 Judge 重新判断（最多 2 次）
  └──────┬──────┘
         │
         ▼
    结构化输出 + JSON 日志 + SSE 事件流
```

### PipelineContext 数据流

所有步骤通过 `PipelineContext` 共享结构化数据，避免上下文窗口污染：

```python
files → parsed_results → tables → structures → cleaned_data → report
```

每个工具通过 `context.get_output(step_index)` 获取前序步骤输出，通过 `context.set_output()` 写入当前结果。

### Self-Improve 自学习机制

BioHermes 在 JSEV 四层闭环之上，增加了跨会话的自学习能力。每次 session 结束后提取执行指标，持久化到 JSON，后续 session 动态优化决策：

```
Session 完成 → SelfImprove.learn() → metrics.json → Judge/Executor 动态调整
```

| 学习维度 | 数据来源 | 反馈目标 |
|---------|---------|---------|
| 工具成功率 | 每步执行结果，按 task_type 分组 | Judge 工具推荐排序（成功率高的优先） |
| Judge 准确度 | 判断类型 vs 最终成功/失败 | Judge 风险提示（历史低准确率类型加 risk_factors） |
| 执行时长分布 | 每步 duration，计算 avg × 3 估算 p95 | Executor 动态超时（替代固定 300s） |

**设计特点**：
- 轻量级 JSON 持久化，无额外数据库依赖
- 冷启动安全：无历史数据时退化为默认策略
- 按任务类型分组统计，避免不同类型互相干扰

### Recovery 三级恢复

```
失败 → Retry (指数退避, 最多 3 次)
     → Degrade (MinerU → PyMuPDF 本地解析)
     → Skip (非关键步骤标记 skipped, 继续执行)
```

---

## 竞品分析

### 赛道二主要参赛方案对比

| 维度 | BioHermes | codezzzsleep | control-sci | 惯导智衡 | palm_data |
|------|-----------|--------------|-------------|---------|-----------|
| **架构** | Judge→Select→Execute→Verify 四层闭环 | Skill-guided LLM Agent + 质量校验 | 14 意图分类 + 4 路径调度 | ReAct Agent + RAG + 知识图谱 | LangGraph 12 节点工作流 |
| **LLM 调用策略** | 集中于 Judge/Verify 两端 | Skill-guided 调度 | 三引擎推理 (API/Ollama/vLLM) | MiniMax + MinerU Cloud API | 多 LLM 协同 |
| **任务理解** | LLM 全局语义分析 + 关键词降级 | Skill 引导 + 规则匹配 | 14 类意图分类器 | ReAct 逐步推理 | 图节点预定义逻辑 |
| **文档解析** | MinerU API + PyMuPDF 双保险 | MinerU CLI + 降级 | MinerU + 253K 公式提取 | MinerU Cloud API | MinerU |
| **结果验证** | 三级自动校验 + 回环 | 页级 provenance + 合计行核验 | 500 题基准评测对比 | 无明确验证机制 | NL2SQL 结果对比 |
| **自学习** | 跨会话指标累积 + 动态优化 | 无 | 无 | 无 | 无 |
| **表格处理** | 跨页合并 + 合并单元格 + 数字一致性 | 表格结构化 + 空结果检测 | 表格结构化 | 表格提取 | NL2SQL 查询 |
| **异常恢复** | Retry→Degrade→Skip 三级 | OCR retry + CLI fallback + text cleanup | 多引擎切换 | 无明确恢复机制 | 节点异常处理 |
| **测试覆盖** | 5 个 Demo 场景 | 17 个案例 + 82% 单测覆盖 | 500 题基准评测 | 356 篇文档实测 | 未公开 |
| **实时性** | SSE 流式推送 | 无 | 无 | SSE 流式推送 | SSE 流式推送 |
| **部署** | Docker 单容器 | CLI-first | RTX 5090 + Docker | Docker + FastAPI | Docker Compose |
| **开源协议** | CC-BY-4.0 | 未明确 | MIT | 未明确 | 未明确 |

### BioHermes 差异化优势

1. **唯一的自验证闭环架构**：赛道中唯一实现 Verify 验证层 + Judge 回环的方案。执行后自动校验结果质量（格式→完整性→一致性三级），验证不通过自动回环重新判断。codezzzsleep 有质量校验但不构成闭环；其他方案均无系统级验证。

2. **LLM 用在关键决策点**：LLM 集中部署在 Judge（任务语义理解）和 Verify（结果质量校验）两个高价值节点，而非每次工具调用都依赖 LLM。对比 ReAct 每步都需要 LLM 推理，BioHermes 的 LLM 调用更精准——只在做决策时调用，不做机械执行。

3. **双保险解析 + 三级恢复**：MinerU API 为主，PyMuPDF 为降级方案，配合 Retry→Degrade→Skip 三级恢复。codezzzsleep 有类似降级策略（OCR retry → CLI fallback），但缺少非关键步骤跳过机制。

4. **数据一致性检查**：Verify 层的 Level 3 一致性验证可以检测数字合计与明细是否匹配，这是财务报表、实验数据等场景的关键需求。codezzzsleep 的合计行核验是同类能力，但 BioHermes 将其集成在自动验证闭环中。

5. **PipelineContext 显式数据流**：步骤间通过结构化 context 传递数据，避免 LLM 上下文窗口污染和信息丢失。

6. **跨会话自学习 (Self-Improve)**：赛道中唯一实现跨会话学习积累的方案。每次执行后自动提取工具成功率、Judge 准确度、执行时长等指标，持久化到 JSON，后续 session 动态调整工具排序、超时策略、风险提示。冷启动安全——无历史数据时退化为默认策略。

---

## 项目结构

```
biohermes/
├── agent/
│   ├── core.py            # Agent 主控: session 生命周期管理
│   ├── judge.py           # Judge 判断层: LLM 语义分析 + 关键词降级
│   ├── planner.py         # Select 选优层: 动态生成执行计划
│   ├── executor.py        # Execute 执行层: 工具调用 + 进度推送
│   ├── verifier.py        # Verify 验证层: 三级自动校验
│   ├── recovery.py        # Recovery 恢复层: 重试→降级→跳过
│   ├── self_improve.py    # Self-Improve 自学习: 跨会话指标累积
│   └── models.py          # 数据模型: Session, Step, ToolCall, JudgeResult
├── llm/
│   ├── client.py          # Anthropic 兼容 LLM 客户端
│   └── prompts.py         # 系统提示词模板
├── tools/
│   ├── base.py            # BaseTool 抽象基类 (统一 execute 接口)
│   ├── mineru_parser.py   # MinerU HTTP API + PyMuPDF 降级
│   ├── table_extractor.py # 表格提取 + 跨页合并
│   ├── structure_extractor.py # 结构化信息抽取
│   ├── data_cleaner.py    # 数据清洗与验证
│   └── report_generator.py # 结构化报告生成
├── pipeline/
│   └── context.py         # PipelineContext 数据传递
├── api/
│   ├── server.py          # FastAPI 服务
│   ├── routes_task.py     # 任务提交/查询/流式端点
│   ├── routes_document.py # 文档解析端点
│   └── sse.py             # SSE 事件管理
├── config.py              # 集中配置 (环境变量)
├── utils/
│   ├── logging.py         # 结构化 JSON 日志
│   └── file_utils.py      # 文件校验、哈希、清理
demos/
├── demo1_complex_pdf.py          # 复杂学术论文解析
├── demo2_multi_step_planning.py  # 多步任务规划 (核心 Demo)
├── demo3_batch_recovery.py       # 批量处理与异常恢复
├── demo4_table_chart.py          # 复杂表格与图表解析
└── demo5_knowledge_pipeline.py   # 端到端知识库 Pipeline
```

---

## 快速开始

### 环境要求

- Python 3.10+
- MinerU API 服务（可选，不可用时自动降级到 PyMuPDF）
- LLM API（可选，不可用时自动降级到关键词匹配）

### 安装

```bash
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env 设置 MINERU_API_URL 和 LLM_API_KEY
```

### 启动 API 服务

```bash
python -m biohermes.api.server
# API: http://0.0.0.0:9091
```

### 运行 Demo

```bash
# 核心 Demo: 多步任务规划 + 自动验证
python demos/demo2_multi_step_planning.py

# 批量处理 + 异常恢复
python demos/demo3_batch_recovery.py
```

### Docker 部署

```bash
docker-compose up -d
# API: http://0.0.0.0:9091
```

---

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 + MinerU 状态 |
| `/api/tools` | GET | 已注册工具列表 |
| `/api/task` | POST | 提交 Agent 任务（自然语言） |
| `/api/task/{id}` | GET | 查询任务状态与结果 |
| `/api/task/{id}/stream` | GET | SSE 实时事件流 |
| `/api/document/parse` | POST | 单文档解析 |
| `/api/document/batch` | POST | 批量文档解析 |

### 任务提交示例

```bash
curl -X POST http://localhost:9091/api/task \
  -H "Content-Type: application/json" \
  -d '{"task": "解析 /path/to/paper.pdf，提取所有表格并验证数字一致性"}'
```

---

## 评测维度覆盖

| 评分项 (分值) | BioHermes 覆盖 |
|--------------|---------------|
| **文档理解与结构化 (20)** | MinerU 解析 + 表格提取（跨页合并）+ 公式提取（LaTeX）+ 结构化抽取 + OCR |
| **难点攻克与创新 (15)** | Judge 智能判断 + Verify 自动验证 + 数据一致性检查 + Self-Improve 跨会话学习 + 双保险解析降级 |
| **Agent 规划与执行 (30)** | Judge→Select→Execute→Verify 四层闭环 + SSE 实时推送 + PipelineContext 数据流 |
| **稳定性与可复现 (20)** | 三级恢复 + 批量容错 + 结构化 JSON 日志 + Docker 一键部署 |
| **开源共享 (15)** | 完整开源 (CC-BY-4.0) + BaseTool 可扩展接口 + 标准化 REST/SSE API |

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent 架构 | Judge→Select→Execute→Verify 四层闭环 |
| LLM | Anthropic 兼容 API（GLM-5.1 via open.bigmodel.cn） |
| 文档解析 | MinerU v3 pipeline backend |
| 降级解析 | PyMuPDF 本地解析 |
| API 框架 | FastAPI + uvicorn |
| 实时通信 | Server-Sent Events (SSE) |
| 容器化 | Docker + docker-compose |

---

## 适用场景

- 学术论文批量解析与结构化（多栏、公式、表格）
- 财务报表智能审核与数字一致性验证
- 工程文档处理与图表理解
- 法律文件结构化与关键信息抽取
- 知识库构建: 文档 → 结构化索引

---

## 开源协议

CC-BY-4.0
