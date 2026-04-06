# 量化投研 Multi-Agent 系统 — 项目总方案

## 项目概述

基于 OpenClaw 的 Multi-Agent 量化投研系统，统一接入新闻、财报、研报、结构化行情与基本面数据，实现每日投研报告、每周复盘总结、投研问答与持仓风险分析，为后续调仓建议和人工审批执行预留架构基础。

**首期不涉及自动交易，不涉及无审批调仓。**

---

## 技术选型（已确认）

| 层级 | 选型 |
|------|------|
| **Agent LLM** | GPT-5.4-mini |
| **Embedding 模型** | voyage-finance-2 |
| **Rerank 模型** | rerank-2.5 |
| **向量库（MVP）** | Chroma |
| **关键词检索** | Elasticsearch（或 Whoosh 作 MVP） |
| **元数据库** | Postgres |
| **控制面** | OpenClaw Gateway |
| **消息渠道** | 飞书（Feishu Bot，长 WebSocket 连接） |
| **量化数据** | Akshare |
| **分析语言** | Python |
| **数据仓（MVP）** | Parquet 文件系统（后期可升级 ClickHouse / Timescale） |
| **文档存储** | 文件系统或 MinIO |

---

## 建设原则

1. **控制面与数据面分离**：OpenClaw 只负责编排，不参与 ETL、索引、量化计算
2. **Agent 负责决策与解释，服务负责确定性计算**：报告和问答由 Agent 生成，回测/因子/风险由程序完成
3. **风控是主链路，不是补丁**：所有涉及仓位的输出必须经过 Risk Agent 或风控引擎
4. **可追踪、可复现、可审计**：每日任务有独立运行记录，结论可回溯到原始证据

---

## 系统架构

### 四层架构

```
交互与调度层：飞书 Bot / OpenClaw Cron / 研究员
OpenClaw 控制层：Gateway → Planner → sessions_spawn → [Knowledge / Quant / Risk] → Report → Critic → 飞书
确定性服务层：Ingestion Service / Parser / RAG Index Builder / Quant Jobs / Risk Engine
数据与存储层：Raw Docs / Postgres / Chroma / BM25 / Market Data / Report Archive
```

### Agent 职责边界

| Agent | 职责 | 工具限制 |
|-------|------|---------|
| **Planner** | 统一入口、意图识别、任务拆解、编排子 Agent | session 工具、消息、cron、有限服务调用 |
| **Knowledge** | RAG 检索规划、混合检索、证据包生成 | 只读检索，无 exec，无 apply_patch |
| **Quant** | 结构化数据获取、指标计算、回测 | 仅限分析脚本执行，启用沙箱 |
| **Risk** | 回撤分析、暴露检查、压力测试 | 同 Quant，无 channel send，启用沙箱 |
| **Report** | 日报/周报生成、飞书卡片输出 | 无原始 ETL 工具 |
| **Critic** | 证据覆盖检查、时效性检查、量化/文本冲突检查 | 只读，无 exec，无 write |

### OpenClaw 配置参考

```json
{
  "agents": {
    "defaults": {
      "tools": { "profile": "coding" },
      "subagents": {
        "maxSpawnDepth": 2,
        "maxChildrenPerAgent": 6,
        "maxConcurrent": 8,
        "runTimeoutSeconds": 900
      }
    },
    "list": [
      { "id": "planner", "default": true, "workspace": "~/.openclaw/workspace-planner" },
      {
        "id": "knowledge",
        "workspace": "~/.openclaw/workspace-knowledge",
        "tools": { "allow": ["read", "web_search", "web_fetch", "sessions_history"], "deny": ["exec", "apply_patch"] }
      },
      { "id": "quant", "workspace": "~/.openclaw/workspace-quant", "sandbox": { "mode": "all", "scope": "agent" } },
      { "id": "risk", "workspace": "~/.openclaw/workspace-risk", "sandbox": { "mode": "all", "scope": "agent" } },
      { "id": "report", "workspace": "~/.openclaw/workspace-report" },
      {
        "id": "critic",
        "workspace": "~/.openclaw/workspace-critic",
        "tools": { "allow": ["read", "sessions_history"], "deny": ["exec", "write", "apply_patch"] }
      }
    ]
  },
  "bindings": [{ "agentId": "planner", "match": { "channel": "feishu", "accountId": "main" } }],
  "channels": {
    "feishu": {
      "enabled": true,
      "defaultAccount": "main",
      "accounts": { "main": { "appId": "cli_xxx", "appSecret": "xxx", "name": "Quant Research Bot" } },
      "streaming": true,
      "blockStreaming": true
    }
  },
  "cron": { "enabled": true, "maxConcurrentRuns": 1 }
}
```

---

## 核心业务流程

### 每日研报流程

```
Cron → Planner
Planner → Ingestion Service（拉取新闻/公告/财报/研报）
Ingestion → Parse/Index（解析、去重、切分、向量化）
Planner → sessions_spawn 并行触发：
  Knowledge Agent → Evidence Pack
  Quant Agent → Quant Output
  Risk Agent → Risk Output
Planner → Report Agent → 日报草稿
Report → Critic Agent → 校验结果
Critic → 飞书推送摘要 + 归档
```

**Critic 降级策略**：Critic 超时（30 秒）时，Report 附带警告标记仍推送，不阻塞链路。

### 飞书问答流程

```
用户提问 → Planner 意图识别
  文档/事件类 → Knowledge Agent
  量化指标类 → Quant Agent
  持仓/回撤类 → Risk Agent
  混合类 → 并行召回 K + Q + R
→ Critic 校验 → 飞书回复（含证据来源）
```

---

## 代码目录结构

```
openclaw-proj/
├── services/
│   ├── ingestion/          # 采集、解析、去重
│   ├── rag/                # 切分、索引、检索 API（voyage-finance-2 embedding，rerank-2.5 rerank）
│   ├── quant/              # Akshare 接入、指标/因子计算脚本
│   └── risk/               # 风险引擎 HTTP 服务（独立部署）
├── openclaw/
│   ├── workspaces/
│   │   ├── planner/        # Planner Workspace
│   │   ├── knowledge/      # Knowledge Workspace
│   │   ├── quant/          # Quant Workspace
│   │   ├── risk/           # Risk Workspace
│   │   ├── report/         # Report Workspace
│   │   └── critic/         # Critic Workspace
│   ├── skills/             # Shared service invocation skills
│   └── runtime/            # OpenClaw runtime bootstrap and sync helpers
├── openclaw.config.json    # OpenClaw 配置（见上方参考）
├── templates/
│   ├── daily_report.md     # 日报模板
│   └── weekly_report.md    # 周报模板
├── docs/
│   ├── openclaw-multi-agent-architecture.md
│   └── project-plan-quant-research.md
└── CLAUDE.md               # 本文件
```

---

## 分阶段实施计划

### 阶段 0：项目启动与技术基础（2026-04-07 ~ 2026-04-24，2.5 周）

**关键交付物：**
- 目标股票池文档（≤50 只 A 股）+ 主题池
- 数据源 SOP（新闻站点、公告来源、Akshare 数据字段清单）
- 技术选型决策文档（LLM: GPT-5.4-mini，Embedding: voyage-finance-2，Rerank: rerank-2.5 ✅）
- OpenClaw Gateway 可运行实例（验证基础路由）
- 飞书 Bot 收到第一条测试消息
- Repo 初始化 + CI 模板 + 代码规范
- 开发/测试环境启动脚本（Postgres + Chroma + Akshare 沙箱）
- 各外部服务 Mock/Stub 规范文档

**验收标准：**
- OpenClaw Gateway 可接收飞书消息并路由到 Planner Agent stub
- Chroma + Postgres 可本地启动并写入测试数据
- Akshare 可拉取目标股票近 1 年行情数据

---

### 阶段 1：数据采集与 RAG MVP（2026-04-27 ~ 2026-05-29，5 周）

#### Sprint 1.1（04-27 ~ 05-08）：采集与解析

| 任务 | 负责 |
|------|------|
| 新闻采集 Spider（≥2 个主流财经站点） | 后端工程师 |
| 公告/财报 PDF 解析（PyMuPDF 或 pdfplumber） | NLP 工程师 |
| 去重逻辑（哈希 + 语义去重） | NLP 工程师 |
| Postgres metadata schema 设计（公司、行业、日期、来源、文档类型） | 后端工程师 |
| 原始文档存储（文件系统或 MinIO） | 后端工程师 |

#### Sprint 1.2（05-11 ~ 05-22）：索引与 Knowledge Agent MVP

| 任务 | 负责 |
|------|------|
| 文档切分（Parent-child chunk，chunk_size ≈ 512 tokens） | NLP 工程师 |
| 构建 Chroma 向量索引（voyage-finance-2 embedding） | NLP 工程师 |
| 构建 BM25 索引 | NLP 工程师 |
| 混合检索 API（Dense + BM25 + rerank-2.5，score 融合） | NLP 工程师 |
| Knowledge Agent 实现（OpenClaw agent，工具：检索 API） | 技术负责人 |

**阶段 1 末里程碑（05-22）：飞书提问 → Planner → Knowledge Agent → 返回带证据 RAG 回答**

**阶段 1 验收：**
- 采集成功率 ≥ 90%（MVP 宽松标准）
- Knowledge Agent 可处理飞书提问，回答包含文档来源和日期
- 检索 P50 延迟 < 5 秒

---

### 阶段 2：量化与风险分析 MVP（2026-06-01 ~ 2026-06-27，4 周）

#### Sprint 2.1（06-01 ~ 06-12）：量化数据接入与分析脚本

| 任务 | 负责 |
|------|------|
| Akshare 数据接入（行情、财务、行业）自动化拉取 | 量化工程师 |
| 数据入仓（Parquet 文件系统） | 量化工程师 |
| 日度指标计算脚本（涨跌幅、换手率、量价关系、均线） | 量化工程师 |
| 因子分析脚本（动量、估值、成长因子 α 版） | 量化工程师 |
| Quant Agent 实现 | 技术负责人 |

#### Sprint 2.2（06-15 ~ 06-27）：风险引擎与 Risk Agent

| 任务 | 负责 |
|------|------|
| 风险指标计算（最大回撤、波动率、Beta、行业集中度） | 量化工程师 |
| 持仓压力测试（历史情景回测） | 量化工程师 |
| 风险引擎 API 封装（独立 HTTP 服务） | 后端工程师 |
| Risk Agent 实现（强制门禁逻辑，无写权限，沙箱隔离） | 技术负责人 |

**阶段 2 末里程碑（06-27）：Planner 并行触发 Knowledge + Quant + Risk，汇总结果，总耗时 < 30 秒**

**阶段 2 验收：**
- Quant Agent 可返回目标股票日度量化摘要
- Risk Agent 可返回回撤和行业暴露分析

---

### 阶段 3：日报、周报与飞书闭环（2026-06-29 ~ 2026-07-31，5 周）

#### Sprint 3.1（06-29 ~ 07-10）：Report Agent + Critic Agent

| 任务 | 负责 |
|------|------|
| 日报模板设计（市场概览 / 重点事件 / 量化信号 / 风险提示） | 项目负责人 + NLP 工程师 |
| Report Agent 实现（拼装 Evidence Pack + Quant Output + Risk Output） | 技术负责人 |
| 飞书消息卡片格式（摘要版 + 归档链接） | 后端工程师 |
| Critic Agent 实现（证据覆盖、时效性、量化/文本冲突检查，含降级策略） | NLP 工程师 |

#### Sprint 3.2（07-13 ~ 07-25）：Cron 调度与完整流程联调

| 任务 | 负责 |
|------|------|
| OpenClaw Cron 配置（每日定时触发完整链路） | 后端工程师 |
| 周报流程实现（汇总 5 日数据、周收益归因、下周观察清单） | NLP 工程师 + 量化工程师 |
| 报告归档服务（Postgres + 文件存储） | 后端工程师 |
| 完整主流程联调（Cron → Planner → K+Q+R → Report → Critic → 飞书） | 全员 |

**阶段 3 末里程碑（07-25）：完整日报从 Cron 触发到飞书推送端对端跑通（无人工干预）**

#### Sprint 3.3（07-28 ~ 07-31）：集成加固

| 任务 | 负责 |
|------|------|
| 失败重试与告警（飞书异常、Agent 超时、采集失败，5 分钟内告警） | 后端工程师 |
| 结构化日志 + 任务成功率监控 | 后端工程师 |
| 密钥与配置管理分离 | 技术负责人 |

**阶段 3 验收：**
- 日报按 Cron 定时自动生成并推送
- 周报每周一自动生成并推送
- 飞书问答有完整链路
- 任务失败 5 分钟内告警触达

---

### 阶段 4：试运行与质量优化（2026-08-03 ~ 2026-08-14，2 周）

| 任务 | 负责 |
|------|------|
| 日报/周报连续 10 个交易日试运行 | 全员监控 |
| 飞书问答案例收集，人工评估准确率（目标 ≥ 80%） | 项目负责人 + NLP 工程师 |
| 采集成功率、日报任务成功率、推送延迟评估 | 后端工程师 |
| 高频问题修复（延迟、证据覆盖率、格式） | 全员 |
| 首期总结报告 + 二期建设建议 | 项目负责人 |

**最终验收标准：**
- 公开资料采集成功率 ≥ 95%
- 日报任务成功率 ≥ 90%
- 关键结论可追溯到证据源
- 飞书连接故障可恢复（支持手动补发）
- 配置、密钥、数据源可独立管理

---

## 后续扩展路线

| 阶段 | 内容 |
|------|------|
| **二期** | 知识图谱增强检索、持仓画像、调仓候选建议、飞书人工审批卡片 |
| **三期** | 纸面交易模拟、策略效果跟踪、用户风险偏好管理 |
| **四期** | 对接执行系统/券商接口、人工确认后半自动执行、全量审计留痕 |

---

## 推荐团队配置（5.5-6.5 人）

| 角色 | 人数 | 主要职责 |
|------|------|---------|
| 项目负责人 | 1 | 范围管理、优先级、业务验收 |
| 技术负责人 | 1 | 架构、OpenClaw 编排、Agent 实现 |
| 后端/平台工程师 | 1-2 | 采集服务、索引服务、飞书接入、调度部署 |
| 量化工程师 | 1 | 指标/因子定义、回测、风险模型 |
| NLP 工程师 | 1 | 文档切分、检索策略、Critic 逻辑 |
| 测试/运维 | 0.5-1 | 监控告警、故障处理 |

> 量化工程师与 NLP 工程师不应由同一人兼任。

---

## 关键风险

| 风险 | 等级 | 应对 |
|------|------|------|
| OpenClaw 平台成熟度不足 | 中 | 阶段 0 必须跑通基础路由验证，提前建立维护方沟通渠道 |
| Critic Agent 成为单点瓶颈 | 中 | 设置 30 秒超时降级策略，超时后附警告标记仍推送 |
| 采集数据合规性 | 中 | 只采集公开免费数据，不爬取明确禁止的网站 |
| 检索质量不足（幻觉风险） | 中 | 混合检索 + rerank-2.5 + 时间过滤 + Critic 校验 + 回答附证据 |
| 量化口径不一致 | 低-中 | 脚本版本化，明确口径与样本范围，独立回测审查 |
| 范围膨胀 | 中 | 一期只做日报/周报/问答/风险分析，持仓诊断和调仓建议放二期 |
