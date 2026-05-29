# BioHermes — MinerU-Powered Data Agent

> **2026 MinerU 数据智能与前沿语料挑战赛 · 赛道二参赛作品**

**BioHermes** 是一个基于 MinerU 工具链的 Data Agent，采用 **Judge → Select → Execute → Verify** 四层架构，具备智能任务判断、最优工具选择、流水线执行和自动验证能力。

---

## 核心架构

```
用户自然语言指令
       │
       ▼
  ┌─────────────┐
  │   Judge     │  ← LLM 分析任务类型、复杂度、文档特征
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │   Select    │  ← 选择最优工具组合和执行策略
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │   Execute   │  → 调用工具执行，PipelineContext 传递数据
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │   Verify    │  ← 自动验证结果，不通过则回环到 Judge
  └──────┬──────┘
         ▼
    结构化输出 + 完整日志
```

### 与传统 Agent 的区别

| 特性 | 传统 Agent | BioHermes |
|------|-----------|-----------|
| 任务理解 | 关键词匹配 | LLM Judge 语义分析 |
| 工具选择 | 固定流程 | Select 层动态选优 |
| 数据流 | 无/硬编码 | PipelineContext 步骤间传递 |
| 结果验证 | 无 | Verify 三级自动校验 |
| 失败处理 | 简单重试 | Judge→Verify 回环 |

---

## 项目结构

```
biohermes/
├── agent/
│   ├── core.py        # Agent 主控
│   ├── judge.py       # Judge 判断层 (LLM + 关键词降级)
│   ├── planner.py     # Select 选优层
│   ├── executor.py    # Execute 执行层
│   ├── verifier.py    # Verify 验证层
│   ├── recovery.py    # Recovery 异常恢复
│   └── models.py      # 数据模型
├── llm/
│   ├── client.py      # Anthropic 兼容 LLM 客户端
│   └── prompts.py     # 系统提示词模板
├── tools/
│   ├── base.py        # BaseTool 抽象基类
│   ├── mineru_parser.py   # MinerU API + PyMuPDF 降级
│   ├── table_extractor.py # 表格提取 + 一致性验证
│   ├── structure_extractor.py # 结构化抽取
│   ├── data_cleaner.py    # 数据清洗
│   └── report_generator.py # 报告生成
├── pipeline/
│   └── context.py     # PipelineContext 数据传递
├── api/
│   ├── server.py      # FastAPI 服务
│   ├── routes_task.py # 任务端点
│   ├── routes_document.py # 文档解析端点
│   └── sse.py         # SSE 事件管理
└── config.py          # 集中配置
```

---

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 启动 API

```bash
python -m biohermes.api.server
# http://0.0.0.0:9091
```

### 运行 Demo

```bash
python demos/demo2_multi_step_planning.py
```

### Docker

```bash
docker-compose up -d
```

---

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 + MinerU 状态 |
| `/api/tools` | GET | 工具列表 |
| `/api/task` | POST | 提交 Agent 任务 |
| `/api/task/{id}` | GET | 查询任务状态 |
| `/api/task/{id}/stream` | GET | SSE 实时事件流 |
| `/api/document/parse` | POST | 单文档解析 |
| `/api/document/batch` | POST | 批量解析 |

---

## 评测维度覆盖

| 评分项 (分值) | 覆盖情况 |
|--------------|---------|
| 文档理解与结构化 (20) | MinerU 解析 + 表格提取 + 公式提取 + 结构化抽取 |
| 难点攻克与创新 (15) | Judge 智能判断 + Verify 自动验证 + 双保险解析 + 数据一致性检查 |
| Agent 规划与执行 (30) | Judge→Select→Execute→Verify 四层架构 + SSE 实时推送 |
| 稳定性与可复现 (20) | 三级恢复 + 批量容错 + JSON 日志 + Docker |
| 开源共享 (15) | 完整开源 + 标准化 API + BaseTool 可扩展 + 详细文档 |

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent 核心 | Judge→Select→Execute→Verify 四层 |
| LLM | Anthropic 兼容 API (GLM-5.1) |
| 文档解析 | MinerU v3 pipeline backend |
| 降级解析 | PyMuPDF 本地 |
| API | FastAPI + uvicorn |
| 实时推送 | Server-Sent Events |

## 开源协议

CC-BY-4.0
