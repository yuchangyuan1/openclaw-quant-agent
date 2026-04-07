# Mock and Stub API Contracts

This document defines repository-safe mock examples for local development and documentation.

All examples below use the current US-market assumptions:

- stock universe: Magnificent 7
- filing source: SEC EDGAR
- market benchmark: SPY
- output language: English

## Common Response Envelope

```json
{
  "success": true,
  "data": {},
  "error": null,
  "timestamp": "2026-04-08T09:00:00+08:00"
}
```

## Ingestion Example

### `POST /api/v1/ingest/trigger`

```json
{
  "source": "all",
  "date": "2026-04-08",
  "stock_codes": ["AAPL", "MSFT"]
}
```

```json
{
  "success": true,
  "data": {
    "job_id": "ingest_20260408_stub",
    "status": "queued",
    "estimated_docs": 14
  }
}
```

## Retrieval Example

### `POST /api/v1/retrieve`

```json
{
  "query": "Apple latest filing",
  "stock_codes": ["AAPL"],
  "doc_types": ["filing"],
  "date_range": {
    "start": "2026-04-01",
    "end": "2026-04-08"
  },
  "top_k": 5,
  "min_score": 0.25
}
```

```json
{
  "success": true,
  "data": {
    "query": "Apple latest filing",
    "results": [
      {
        "doc_id": "doc_stub_001",
        "title": "[Stub] Apple files quarterly report",
        "source": "sec_edgar",
        "url": "https://www.sec.gov/Archives/doc_stub_001.html",
        "published_at": "2026-04-08T07:45:00+08:00",
        "company_code": "AAPL",
        "snippet": "Apple discussed services growth, hardware demand, and capital return priorities.",
        "score": 0.92,
        "retrieval_method": "stub"
      }
    ],
    "total_retrieved": 1
  }
}
```

## Quant Example

### `POST /api/v1/quant/daily`

```json
{
  "stock_codes": ["AAPL", "NVDA"],
  "date": "2026-04-08",
  "indicators": []
}
```

```json
{
  "success": true,
  "data": {
    "trade_date": "2026-04-07",
    "market_summary": {
      "tracked_avg_pct_change": 0.85,
      "advancing_stocks": 2,
      "declining_stocks": 0,
      "coverage_count": 2
    },
    "stocks": [
      {
        "code": "AAPL",
        "name": "Apple Inc.",
        "close": 210.0,
        "pct_change": 1.23,
        "ma_signal": "bullish",
        "pe_ttm": 22.3,
        "roe": 31.5,
        "data_date": "2026-04-07"
      }
    ]
  }
}
```

## Risk Example

### `POST /api/v1/risk/check`

```json
{
  "portfolio": [
    { "code": "AAPL", "weight": 0.40 },
    { "code": "MSFT", "weight": 0.35 },
    { "code": "NVDA", "weight": 0.25 }
  ],
  "benchmark": "SPY",
  "lookback_days": 90,
  "run_scenarios": true
}
```

```json
{
  "success": true,
  "data": {
    "risk_level": "MEDIUM",
    "max_drawdown_90d": -0.12,
    "volatility_annual": 0.24,
    "beta": 1.05,
    "top_industry_exposure": {
      "industry": "Technology",
      "weight": 0.60
    },
    "alerts": [
      "Industry concentration is elevated: Technology at 60.00%."
    ],
    "scenario_loss_estimate": {
      "dotcom_style_shock": -0.18,
      "covid_style_shock": -0.12,
      "rate_shock": -0.08
    }
  }
}
```

## Planner Example

### `POST /api/v1/planner/query`

```json
{
  "message": "Apple latest filing",
  "refresh_index": false
}
```

```json
{
  "success": true,
  "data": {
    "intent": "DOC_QA",
    "reply_markdown": "**Apple latest filing**\n\nCurrent evidence indicates services growth remained resilient [E001].",
    "critic_status": "PASS",
    "evidence_count": 1,
    "matched_companies": ["AAPL"],
    "matched_themes": ["Consumer Platforms"],
    "collaboration_agents": ["planner", "knowledge"]
  }
}
```
