# OpenClaw US Market Research Project Plan

## 1. Project Scope

This project has been migrated from an A-share quant research prototype to an English-language US market research system.

Current scope:

- market universe: `Magnificent 7`
- market data: `yfinance`
- filing and disclosure source: `SEC EDGAR`
- output language: English
- orchestration framework: `OpenClaw`
- ethics orientation: evidence grounding, critic review, action boundaries, and human oversight

## 2. Current Delivered Capabilities

### 2.1 Ingestion

- SEC EDGAR submissions ingestion
- normalized filing metadata
- target-pool incremental collection jobs
- document persistence and metadata storage

### 2.2 Retrieval and Knowledge

- document chunking
- Chroma indexing
- graph-aware retrieval
- evidence pack generation
- filing-oriented query rewriting

### 2.3 Structured Analysis

- yfinance-backed daily price cache
- technical indicators
- valuation factors
- financial factors
- industry-relative comparison
- composite scoring

### 2.4 Risk

- portfolio volatility
- drawdown analysis
- beta estimation
- industry concentration
- scenario loss estimates

### 2.5 Reports and Governance

- daily report generation
- weekly report generation
- critic review
- run logs
- replay support
- alert summary support

## 3. Current OpenClaw Execution Model

Implemented collaboration paths:

- `DOC_QA`: `Planner -> Knowledge`
- `QUANT_QUERY`: `Planner -> Quant`
- `RISK_QUERY`: `Planner -> Risk`
- `MIXED_QUERY`: `Planner -> parallel(Knowledge, Quant, Risk)`
- `DAILY_REPORT`: `Planner -> parallel(Knowledge, Quant, Risk) -> Report -> Critic`
- `WEEKLY_REPORT`: `Planner -> Knowledge + Quant + Risk -> Report -> Critic`

This is already a working OpenClaw-native hybrid model:

- OpenClaw manages workspaces, routing, binding, and orchestration contracts
- deterministic FastAPI services perform ingestion, retrieval, analysis, risk, reporting, and review

## 4. Storage and Retrieval Model

- `Postgres`
  - structured metadata, reports, logs, graph tables, metric snapshots, risk snapshots
- `Lightweight Graph`
  - entity and relation layer for company, theme, industry, and filing context
- `Chroma`
  - vector retrieval for indexed chunks
- `data/market`
  - local yfinance cache
- `data/financials`
  - local fundamental cache

## 5. Ethics-Oriented Output Contract

Every major planner response or report flow is expected to surface:

- `evidence_status`
- `data_freshness`
- `critic_status`
- `risk_status`
- `action_boundary`
- `human_approval_required`
- `accountability_trail`

The critic layer remains mandatory for report workflows.

## 6. Validation Status

Current local validation status after the US-market migration:

- `python -m compileall services scripts tests` passes
- `pytest -q -p no:cacheprovider tests` passes
- test suite result: `78 passed`

## 7. Remaining Optional Enhancements

These are no longer required for MVP completion, but remain valid future work:

1. deeper OpenClaw runtime `sessions_spawn` execution instead of service-side parallel contracts
2. richer SEC filing body extraction beyond submission metadata and summary text
3. broader US stock universe beyond the Magnificent 7
4. stronger news source coverage beyond EDGAR-centric document intake
5. more advanced approval and governance workflows
