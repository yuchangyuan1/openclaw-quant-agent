# 项目执行计划

基线文档：

- [Agent.md](/D:/yuchangyuan/Documents/openclaw-proj/Agent.md)
- [project-plan-quant-research.md](/D:/yuchangyuan/Documents/openclaw-proj/project-plan-quant-research.md)

## 阶段划分

### 阶段 0：项目定义与技术准备

- 目标：
  - 统一技术方案、目录结构、Agent 边界与 OpenClaw 编排
  - 完成本地基础设施与 Gateway 可运行状态
- 当前状态：已完成
- 已完成内容：
  - OpenClaw 六个 agent 工作区与 Feishu 路由
  - Postgres / Chroma / Quant 样例数据 / 服务冒烟验证
  - README、CI、测试与阶段 0 验收脚本

### 阶段 1：数据采集与 RAG MVP

- 目标：
  - 完成公开资料采集链路
  - 完成解析、去重、切分、索引和基础检索
  - 让 Knowledge Agent 可以返回带证据问答
- 当前状态：进行中
- 已完成内容：
  - Eastmoney / 10jqka 新闻采集
  - Eastmoney 公告采集
  - 原文落盘与元数据存储
  - Chroma 索引与关键词 + 向量混合检索
  - Planner DOC_QA 本地最小编排链路
  - Planner DOC_QA 结构化研究摘要输出（命中公司 / 命中主题 / 证据数量）
  - stock-aware retrieval：使用 `primary_company_code` + `matched_stocks` 提升个股命中率
  - 公司词项识别与过滤：支持股票池外公司问法，降低公告检索误召回
  - Planner 服务化入口：新增 `/api/v1/planner/query`，作为 OpenClaw 消息链路的稳定本地调用面
- 本阶段剩余关键项：
  - Query rewrite / Evidence Pack / synthesis 继续增强
  - 将 OpenClaw Planner agent 的实际执行流程收敛到 `planner` 服务入口

### 阶段 2：量化与风险分析 MVP

- 目标：
  - 接入结构化行情与指标计算
  - 完成 Risk Engine 基础能力
  - 让 Quant / Risk Agent 具备最小可用输出
- 当前状态：进行中
- 已完成内容：
  - 本地行情读取层：统一读取 `data/market/*.parquet`
  - Quant daily summary：真实 close / pct_change / MA / momentum / volatility 输出
  - Quant batch hist：本地切片 + 缺失时 Akshare 回补
  - Quant factor：`momentum_1m` / `momentum_3m` / `volatility_1m` / `price_rank_1y`
  - Risk check：组合波动率 / 最大回撤 / beta / 行业暴露 / 场景损失估算
  - Risk drawdown：个股最大回撤 / 当前回撤 / 恢复天数
- 本阶段剩余关键项：
  - 接入更完整的估值 / 基本面因子，替换当前 `None` 的估值字段
  - 将 Quant / Risk Agent 的实际执行流程进一步收敛到 Planner 主流程

### 阶段 3：日报、周报与飞书闭环

- 目标：
  - 打通日报 / 周报生成、校验与飞书推送
  - 完成 Planner / Report / Critic 主流程联调
- 当前状态：进行中
- 已完成内容：
  - Report 服务：`/api/v1/report/build`
  - Critic 服务：`/api/v1/critic/review`
  - Planner 本地日报入口：`/api/v1/planner/daily-report`
  - Planner 主入口已可直接路由 `DOC_QA / DAILY_REPORT / WEEKLY_REPORT`
  - 本地日报闭环 demo：`Planner -> Knowledge -> Quant -> Risk -> Report -> Critic`
  - Planner 本地周报入口：`/api/v1/planner/weekly-report`
  - 本地周报闭环 demo：基于已归档日报汇总生成 weekly report，并完成 Critic 校验
  - Report / Critic agent 指令已收敛到本地服务入口并同步到 OpenClaw 运行态
- 本阶段剩余关键项：
  - Planner / Report / Critic 的更多主流程联调
  - 飞书推送与线上闭环验证

### 阶段 4：试运行与优化

- 目标：
  - 稳定性、重试、观测、质量评估
  - 为第二阶段持仓诊断与调仓建议预留升级路径
- 当前状态：进行中
- 已完成内容：
  - Report pipeline 已接入 `run_logs` 运行记录
  - 日报 / 周报关键步骤已接入基础重试
  - Planner 观测入口：`/api/v1/planner/run-logs`
  - Planner 重放入口：`/api/v1/planner/run-logs/replay`
  - Planner 告警摘要入口：`/api/v1/planner/alerts/summary`
  - 本地运行日志查看脚本：`scripts/show_run_logs.py`
  - 本地告警摘要脚本：`scripts/show_alert_summary.py`
- 本阶段剩余关键项：
  - 更细粒度告警分级与自动通知
  - 质量评估指标与长期趋势观测

## 当前执行顺序

1. 完成阶段 1 的 Knowledge MVP 闭环
2. 进入阶段 2，补 Quant Jobs 与 Risk Engine
3. 再进入阶段 3，做日报/周报/飞书闭环
4. 最后做阶段 4 试运行和优化

## 本轮执行项

- 新增阶段计划文档
- 继续推进 Knowledge MVP：
  - Query rewrite
  - Evidence Pack 组装
  - 问答合成输出
  - Planner DOC_QA 串联
