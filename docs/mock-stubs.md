# Mock/Stub 服务接口契约 v1.0

> 阶段 0 中所有服务均运行 stub 实现，本文件是 Agent 调用和服务实现的唯一接口规范。  
> 阶段 1/2 逐步替换为真实实现，接口保持向后兼容。

---

## 端口分配

| 服务 | 端口 | 说明 |
|------|------|------|
| ingestion | 8001 | 采集与解析服务 |
| rag | 8002 | 检索服务（向量 + BM25） |
| quant | 8003 | 量化分析服务 |
| risk | 8004 | 风险引擎服务 |
| chroma | 8000 | Chroma 向量库（docker-compose 启动） |

---

## 通用响应格式

所有 API 均使用以下包装格式：

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "timestamp": "2026-04-07T08:15:00+08:00"
}
```

失败时：
```json
{
  "success": false,
  "data": null,
  "error": "错误描述",
  "timestamp": "2026-04-07T08:15:00+08:00"
}
```

---

## 1. Ingestion 服务（:8001）

### GET /health

```json
{ "status": "ok", "service": "ingestion", "version": "0.1.0-stub" }
```

### POST /api/v1/ingest/trigger

触发一次数据采集任务（异步，立即返回 job_id）。

**请求：**
```json
{
  "source": "eastmoney",       // eastmoney | sse | szse | all
  "date": "2026-04-07",        // 可选，默认为当天
  "stock_codes": ["600519", "000001"]  // 可选，为空则采集全部
}
```

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "job_id": "ingest_20260407_001",
    "status": "queued",
    "estimated_docs": 120
  }
}
```

### GET /api/v1/ingest/status/{job_id}

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "job_id": "ingest_20260407_001",
    "status": "completed",
    "docs_collected": 118,
    "docs_failed": 2,
    "started_at": "2026-04-07T08:30:00+08:00",
    "finished_at": "2026-04-07T08:35:42+08:00"
  }
}
```

### GET /api/v1/documents

**查询参数：** `date`, `source`, `stock_code`, `doc_type`, `limit`（默认 20），`offset`（默认 0）

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "total": 1,
    "items": [
      {
        "id": "doc_stub_001",
        "source": "eastmoney",
        "doc_type": "news",
        "title": "[测试] 贵州茅台发布2026年一季报，净利润同比增长12%",
        "url": "https://finance.eastmoney.com/stub/001.html",
        "company_code": "600519",
        "published_at": "2026-04-07T07:45:00+08:00",
        "is_indexed": true
      }
    ]
  }
}
```

---

## 2. RAG 服务（:8002）

### GET /health

```json
{ "status": "ok", "service": "rag", "version": "0.1.0-stub" }
```

### POST /api/v1/retrieve

混合检索（Dense + BM25 + Rerank），返回带评分的证据包。

**请求：**
```json
{
  "query": "贵州茅台一季报净利润",
  "stock_codes": ["600519"],           // 可选，限定股票范围
  "doc_types": ["news", "announcement"],  // 可选
  "date_range": {
    "start": "2026-03-31",
    "end": "2026-04-07"
  },
  "top_k": 5,                          // 返回条数，默认 5
  "min_score": 0.7                     // 最低相关度分数
}
```

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "query": "贵州茅台一季报净利润",
    "results": [
      {
        "doc_id": "doc_stub_001",
        "title": "[测试] 贵州茅台发布2026年一季报，净利润同比增长12%",
        "source": "eastmoney",
        "url": "https://finance.eastmoney.com/stub/001.html",
        "published_at": "2026-04-07T07:45:00+08:00",
        "company_code": "600519",
        "snippet": "贵州茅台今日发布2026年一季报，实现营业收入XXX亿元，净利润XXX亿元，同比增长12%……（stub 数据）",
        "score": 0.92,
        "retrieval_method": "dense+bm25+rerank"
      }
    ],
    "total_retrieved": 1
  }
}
```

### POST /api/v1/index/build

触发索引重建任务（异步）。

**请求：**
```json
{
  "doc_ids": ["doc_stub_001"],   // 可选，为空则全量重建
  "force_rebuild": false
}
```

**响应（stub）：**
```json
{
  "success": true,
  "data": { "job_id": "index_20260407_001", "status": "queued" }
}
```

---

## 3. Quant 服务（:8003）

### GET /health

```json
{ "status": "ok", "service": "quant", "version": "0.1.0-stub" }
```

### POST /api/v1/quant/daily

获取目标股票的日度量化摘要。

**请求：**
```json
{
  "stock_codes": ["600519", "000001", "300750"],
  "date": "2026-04-07",          // 可选，默认最新交易日
  "indicators": ["price", "volume", "ma", "momentum"]  // 可选，默认全部
}
```

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "trade_date": "2026-04-07",
    "market_summary": {
      "sh300_pct_change": 0.85,
      "total_volume_billion": 8523.4,
      "advancing_stocks": 2891,
      "declining_stocks": 1205
    },
    "stocks": [
      {
        "code": "600519",
        "name": "贵州茅台",
        "close": 1780.00,
        "pct_change": 1.23,
        "volume": 125430,
        "turnover_rate": 0.21,
        "ma5": 1762.4,
        "ma20": 1745.8,
        "ma_signal": "bullish",
        "momentum_5d": 2.1,
        "pe_ttm": 28.5,
        "pb": 8.2,
        "data_date": "2026-04-07"
      }
    ]
  }
}
```

### POST /api/v1/quant/batch_hist

批量拉取历史行情并存储（触发 Akshare 调用）。

**请求：**
```json
{
  "stock_codes": ["600519"],
  "start_date": "2025-04-07",
  "end_date": "2026-04-07",
  "adjust": "qfq"
}
```

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "job_id": "batch_hist_20260407_001",
    "status": "completed",
    "saved_files": ["data/market/600519_daily.parquet"]
  }
}
```

### POST /api/v1/quant/factor

计算因子值（动量/估值/成长）。

**请求：**
```json
{
  "stock_codes": ["600519"],
  "factors": ["momentum_1m", "pe_rank", "roe_growth"],
  "date": "2026-04-07"
}
```

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "date": "2026-04-07",
    "factors": [
      {
        "code": "600519",
        "momentum_1m": 3.2,
        "pe_rank": 0.65,
        "roe_growth": 0.12
      }
    ]
  }
}
```

---

## 4. Risk 服务（:8004）

### GET /health

```json
{ "status": "ok", "service": "risk", "version": "0.1.0-stub" }
```

### POST /api/v1/risk/check

对给定投资组合执行风险检查，返回标准 Risk Output。

**请求：**
```json
{
  "portfolio": [
    { "code": "600519", "weight": 0.05 },
    { "code": "300750", "weight": 0.08 }
  ],
  "benchmark": "000300",
  "lookback_days": 90,
  "run_scenarios": true
}
```

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "risk_level": "MEDIUM",
    "max_drawdown_90d": -0.12,
    "volatility_annual": 0.24,
    "beta": 1.05,
    "top_industry_exposure": {
      "industry": "电力设备",
      "weight": 0.28
    },
    "industry_breakdown": [
      { "industry": "电力设备", "weight": 0.28 },
      { "industry": "食品饮料", "weight": 0.18 },
      { "industry": "银行", "weight": 0.15 }
    ],
    "alerts": [],
    "scenario_loss_estimate": {
      "2015_crash": -0.18,
      "2018_trade_war": -0.12,
      "2022_russia_ukraine": -0.08
    },
    "generated_at": "2026-04-07T08:20:00+08:00"
  }
}
```

### POST /api/v1/risk/drawdown

仅计算回撤分析（轻量接口）。

**请求：**
```json
{
  "stock_codes": ["600519", "300750"],
  "lookback_days": 90
}
```

**响应（stub）：**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "code": "600519",
        "max_drawdown": -0.08,
        "current_drawdown": -0.03,
        "recovery_days": null
      }
    ]
  }
}
```

---

## Stub 行为约定

1. **所有 stub 均立即返回**，不模拟网络延迟（测试时可通过配置添加）
2. **stub 数据标记**：所有 stub 响应中的 name/title 字段含 `[测试]` 或 `stub` 标记，便于区分
3. **错误模拟**：通过请求参数 `?force_error=true` 触发 500 错误响应，用于测试降级逻辑
4. **阶段替换**：阶段 1 开始逐步替换 `mock_handler.py` 中的实现，接口不变
