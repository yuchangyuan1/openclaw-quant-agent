# OpenClaw US Market Research System

## Project Overview

OpenClaw US Market Research System is an English-language, evidence-grounded, ethics-aware multi-agent decision support project built on OpenClaw.

The current implementation targets the US equity market and uses:

- `yfinance` for market and fundamental snapshots
- `SEC EDGAR` for public filings ingestion
- the `Magnificent 7` as the default stock universe

The system is designed for research support, not autonomous execution. Every major output is routed through evidence retrieval, risk review, critic review, and action-boundary labeling.

## Project Architecture

The project uses a hybrid architecture:

- `OpenClaw` as the control plane
- deterministic `FastAPI` services as the execution plane
- `Postgres + Lightweight Graph + Chroma` as the storage and retrieval plane

### Core Services

- `ingestion`
  - collects SEC EDGAR filing metadata and normalized document records
- `rag`
  - builds chunked retrieval indexes and graph-aware evidence packs
- `planner`
  - the single entry point for user queries, report routing, and agent collaboration
- `quant`
  - structured technical, valuation, and fundamental analysis based on yfinance-backed caches
- `risk`
  - portfolio risk, drawdown, concentration, beta, and scenario analysis
- `report`
  - daily and weekly markdown report generation
- `critic`
  - mandatory evidence, freshness, consistency, and overstatement review

### OpenClaw Layer

The OpenClaw-native orchestration layer lives under:

- `openclaw/workspaces/`
- `openclaw/skills/`
- `openclaw/runtime/`

Current collaboration paths:

- `DOC_QA`: `Planner -> Knowledge`
- `QUANT_QUERY`: `Planner -> Quant`
- `RISK_QUERY`: `Planner -> Risk`
- `MIXED_QUERY`: `Planner -> parallel(Knowledge, Quant, Risk)`
- `DAILY_REPORT`: `Planner -> parallel(Knowledge, Quant, Risk) -> Report -> Critic`
- `WEEKLY_REPORT`: `Planner -> Knowledge + Quant + Risk -> Report -> Critic`

### Data and Storage

- `Postgres`
  - documents, run logs, reports, graph entities, graph relations, metric snapshots, risk snapshots
- `Lightweight Graph`
  - entity and relation context for companies, industries, themes, filings, and evidence links
- `Chroma`
  - vector retrieval for indexed document chunks
- local caches
  - `data/market`
  - `data/financials`
  - `data/raw`
  - `data/reports`

## Ethics and Governance

The project is aligned to an ethics-oriented AI workflow.

Each major response includes:

- evidence status
- data freshness
- critic status
- action boundary
- human approval requirement
- accountability trail

The critic layer checks:

1. whether key claims are supported by evidence
2. whether data freshness is explicit
3. whether quant and risk outputs conflict
4. whether overstatement language appears
5. whether the action boundary is appropriate

## Usage

### Prerequisites

- Python 3.11+
- Docker Desktop
- PowerShell on Windows
- optional: OpenClaw CLI and Feishu credentials for interactive channel testing

### 1. Configure the Environment

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and confirm at least:

- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `SEC_USER_AGENT`
- optional model keys for live provider-backed workflows

### 2. Start the Full Stack

```powershell
docker compose up -d
```

This starts:

- `postgres`
- `chroma`
- `adminer`
- `ingestion`
- `rag`
- `quant`
- `risk`
- `planner`
- `report`
- `critic`

Stop the stack with:

```powershell
docker compose down
```

### 3. Initialize and Verify

```powershell
python scripts/init_db.py
python scripts/verify_stack.py
```

### 4. Fetch Sample Market Data

```powershell
python scripts/fetch_sample_data.py
```

This fetches cached daily data for the Mag 7 and `SPY`.

### 5. Run the Smoke Test

```powershell
python scripts/run_phase0_smoke.py
```

### 6. Run the Full Test Suite

```powershell
pytest -q -p no:cacheprovider tests
```

### 7. Optional OpenClaw Runtime Sync

```powershell
powershell -ExecutionPolicy Bypass -File .\openclaw\runtime\bootstrap.ps1 -SkipGatewayRestart
```

### 8. Example Local Queries

```powershell
python scripts/run_planner_demo.py "Apple latest filing"
python scripts/run_quant_demo.py --stock-code AAPL --mode daily
python scripts/run_risk_demo.py --holding AAPL:0.4 --holding MSFT:0.35 --holding NVDA:0.25 --mode check
python scripts/run_daily_report_demo.py --date 2026-04-08 --stock-code AAPL --stock-code MSFT
```

## Repository Structure

```text
services/     FastAPI services and business logic
scripts/      setup, sync, validation, and demo scripts
docs/         plans, architecture, and transformation notes
templates/    report templates
tests/        regression and smoke tests
openclaw/     OpenClaw workspaces, skills, and runtime helpers
data/         local runtime caches and generated artifacts
```
