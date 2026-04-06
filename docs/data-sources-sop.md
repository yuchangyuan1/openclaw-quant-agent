# 数据源 SOP v1.0

> 更新日期：2026-04-07

---

## 一、新闻与公告采集源

### 1.1 新闻来源

| 来源 | 域名 | 采集类型 | 频率 | 备注 |
|------|------|------|------|------|
| 东方财富 | eastmoney.com | 财经新闻、个股公告、研报摘要 | 每个交易日 2 次（8:30, 16:00） | 公开免费内容，遵守 robots.txt |
| 同花顺 | 10jqka.com.cn | 财经新闻、个股快讯 | 每个交易日 2 次（8:30, 16:00） | 公开免费内容 |
| 新浪财经 | finance.sina.com.cn | 财经新闻 | 每个交易日 1 次（16:00） | 辅助来源 |

### 1.2 公告来源（优先通过 Akshare 获取）

| 来源 | 方式 | 采集内容 | 频率 |
|------|------|------|------|
| 上海证券交易所 | `ak.stock_notice_report` | 年报/半年报/季报/重大事项公告 | 每个交易日 16:30 后 |
| 深圳证券交易所 | `ak.stock_notice_report` | 同上 | 每个交易日 16:30 后 |
| 上市公司公告（东财） | HTTP 爬取 | PDF 原文 | 按需触发，公告发布后 30 分钟内 |

### 1.3 采集合规原则

- 只采集公开免费内容，不采集需要付费订阅的内容
- 遵守目标网站的 robots.txt 规则
- 请求间隔不低于 2 秒，避免对目标服务器造成压力
- 不采集任何个人隐私数据

---

## 二、Akshare 数据字段清单

### 2.1 日度行情数据

| 函数名 | 用途 | 主要字段 | 更新频率 | 备注 |
|--------|------|----------|----------|------|
| `ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date, adjust="qfq")` | A 股日行情（前复权） | 日期/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率 | 交易日收盘后 | symbol 格式：`000001`（不含后缀） |
| `ak.index_zh_a_hist(symbol, period="daily", start_date, end_date)` | A 股指数日行情 | 日期/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/换手率 | 交易日收盘后 | symbol：`sh000300`（沪深300）等 |
| `ak.stock_zh_a_hist_min_em(symbol, period="5", adjust="qfq")` | A 股分钟行情 | 时间/开盘/收盘/最高/最低/成交量/成交额 | 实时（盘中） | 仅交易时段有效 |

### 2.2 基本面与财务数据

| 函数名 | 用途 | 主要字段 | 更新频率 | 备注 |
|--------|------|----------|----------|------|
| `ak.stock_financial_abstract_ths(symbol, indicator)` | 财务摘要（同花顺） | 报告期/营收/净利润/净利润增速/营收增速/毛利率/净利率/ROE/EPS | 季度（财报发布后） | indicator：按报告期类型 |
| `ak.stock_individual_info_em(symbol)` | 个股基本信息 | 总市值/流通市值/市盈率(TTM)/市净率/所属行业/上市日期/总股本/流通股本 | 交易日 | 静态数据，每日刷新 |
| `ak.stock_financial_balance_ths(symbol, indicator)` | 资产负债表 | 总资产/净资产/货币资金/总负债/资产负债率 | 季度 | |
| `ak.stock_financial_cash_ths(symbol, indicator)` | 现金流量表 | 经营/投资/融资现金流净额 | 季度 | |

### 2.3 行业与板块数据

| 函数名 | 用途 | 主要字段 | 更新频率 |
|--------|------|----------|----------|
| `ak.stock_board_industry_name_em()` | 申万行业板块列表 | 板块名称/板块代码 | 不常变 |
| `ak.stock_board_industry_hist_em(symbol, period, start_date, end_date, adjust)` | 行业板块历史行情 | 日期/开盘/收盘/涨跌幅/成交量/成交额 | 交易日 |
| `ak.stock_board_concept_name_em()` | 概念板块列表 | 板块名称/板块代码 | 不常变 |

### 2.4 市场宏观数据

| 函数名 | 用途 | 主要字段 | 更新频率 |
|--------|------|----------|----------|
| `ak.stock_zh_a_spot_em()` | A 股实时行情全量 | 代码/名称/最新价/涨跌幅/成交量/成交额/换手率/市盈率/市净率 | 交易时段实时 |
| `ak.macro_china_nbs_nation_get(indicator)` | 宏观经济指标（国家统计局） | 时间/数值 | 月度/季度 |
| `ak.rate_interbank(market, symbol, indicator)` | 银行间利率 | 日期/利率 | 交易日 |

### 2.5 龙虎榜与资金流向

| 函数名 | 用途 | 主要字段 | 更新频率 |
|--------|------|----------|----------|
| `ak.stock_fund_flow_individual(symbol)` | 个股资金流向 | 日期/主力净流入/散户净流入/大单净流入 | 交易日 |
| `ak.stock_lhb_detail_em(date)` | 龙虎榜明细 | 代码/名称/上榜原因/买入/卖出金额 | 交易日 |

---

## 三、数据路径约定

```
openclaw-proj/
└── data/
    ├── raw/                          # 原始采集数据（不清洗）
    │   ├── eastmoney/
    │   │   └── {YYYY-MM-DD}/
    │   │       └── {doc_id}.json     # 新闻原始 JSON（含标题/URL/内容/发布时间）
    │   ├── sse/                      # 上交所公告
    │   │   └── {YYYY-MM-DD}/
    │   │       └── {doc_id}.json
    │   └── szse/                     # 深交所公告
    │       └── {YYYY-MM-DD}/
    │           └── {doc_id}.json
    ├── market/                       # Akshare 行情数据（Parquet）
    │   ├── {code}_1y.parquet         # 近 1 年日行情（验收脚本产物）
    │   ├── {code}_daily.parquet      # 持续更新的日行情文件
    │   └── index_{code}_daily.parquet  # 指数行情
    ├── financials/                   # 财务数据（Parquet）
    │   └── {code}_financials.parquet
    └── reports/                      # 生成的日报/周报归档
        ├── daily/
        │   └── {YYYY-MM-DD}.md
        └── weekly/
            └── {YYYY-W##}.md
```

### 文件命名规则

- 股票代码统一使用 6 位数字，不含交易所后缀（如 `600519`，不用 `600519.SH`）
- 日期格式统一：`YYYY-MM-DD`（如 `2026-04-07`）
- doc_id 生成规则：`{source}_{timestamp}_{hash[:8]}`（如 `eastmoney_20260407_a1b2c3d4`）

---

## 四、去重 SOP

### 4.1 文档级去重（阶段 0 实现）

- 计算文档全文的 SHA-256 哈希
- 写入 Postgres `documents.content_hash` 字段
- 采集时先查询该 hash 是否存在，存在则跳过

### 4.2 语义去重（阶段 1 实现）

- 对新文档计算 voyage-finance-2 embedding
- 在向量库中查询 cosine similarity > 0.92 的文档
- 若存在相似文档，记录关联关系，不重复建索引
- 保留最新文档，旧文档标记 `is_duplicate = true`

### 4.3 公告去重

- 以上市公司代码 + 公告标题 + 发布日期作为联合唯一键
- 同一天同一公司的同名公告视为重复

---

## 五、数据保留策略

| 数据类型 | 原始格式保留时长 | 解析后保留时长 |
|------|------|------|
| 新闻原始 HTML/JSON | 30 天 | 永久（文本 + Postgres 元数据） |
| 公告 PDF | 永久 | 永久 |
| 日行情 Parquet | 永久 | 永久 |
| 生成报告 | 永久 | 永久 |
| 向量索引 | 永久（定期重建） | - |

---

## 六、采集调度规则

| 任务 | 触发时间（Asia/Shanghai） | 方式 |
|------|------|------|
| 晨间采集（新闻/公告/行情快报） | 工作日 08:30 | OpenClaw Cron |
| 收盘数据采集（行情/财务更新） | 工作日 16:30 | OpenClaw Cron |
| 日报生成触发 | 工作日 08:15（收盘数据采集后次日） | OpenClaw Cron |
| 周报生成触发 | 每周一 08:00 | OpenClaw Cron |
| 公告实时监控（阶段 2） | 工作日 09:00-15:30 | 轮询，间隔 10 分钟 |

---

## 七、告警规则

| 异常 | 阈值 | 告警方式 |
|------|------|------|
| 采集成功率低 | < 90%（单次任务） | 飞书告警 |
| Akshare 拉取失败 | 连续 3 次 | 飞书告警 |
| 任务超时 | 单任务 > 15 分钟 | 飞书告警 |
| 数据库连接失败 | 任意一次 | 飞书告警 |
