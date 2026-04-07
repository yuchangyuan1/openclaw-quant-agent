# Target Stock Pool v2.0

> Updated: 2026-04-08  
> Scope: U.S. equities  
> Core universe: Magnificent 7

## Selection Principles

- Large-cap, high-liquidity U.S. equities
- Consistently covered by public filings and market data
- Representative of AI infrastructure, cloud, consumer platforms, and EVs
- Suitable for evidence-grounded, ethics-aware research workflows

## Core Stock Pool

| Ticker | Company | Industry | Role | Reason for Inclusion | CIK |
| --- | --- | --- | --- | --- | --- |
| AAPL | Apple Inc. | Consumer Electronics | Core | Global consumer hardware platform with strong ecosystem and supply-chain significance | 0000320193 |
| MSFT | Microsoft Corporation | Software & Cloud | Core | Enterprise software and cloud leader; central to AI infrastructure and productivity markets | 0000789019 |
| GOOGL | Alphabet Inc. | Internet Platforms | Core | Search, advertising, cloud, and generative AI platform exposure | 0001652044 |
| AMZN | Amazon.com, Inc. | E-Commerce & Cloud | Core | Consumer platform plus AWS; strong signal for cloud demand and logistics | 0001018724 |
| META | Meta Platforms, Inc. | Digital Advertising | Core | Social platform, advertising demand, and open-model AI ecosystem exposure | 0001326801 |
| NVDA | NVIDIA Corporation | Semiconductors & AI Hardware | Core | Foundational AI compute supplier and key semiconductor benchmark | 0001045810 |
| TSLA | Tesla, Inc. | EVs & Clean Energy | Core | EV, autonomy, and industrial AI exposure with high public-information intensity | 0001318605 |

## Research Themes

### Theme 1: AI Infrastructure

Representative names: NVDA, MSFT, GOOGL, META

Key events to monitor:
- AI model launches and product rollouts
- Data center expansion and GPU demand signals
- Cloud capex guidance
- AI regulation and disclosure language in SEC filings

### Theme 2: Consumer Platforms

Representative names: AAPL, AMZN, GOOGL, META

Key events to monitor:
- Device launches and ecosystem monetization
- Advertising demand trends
- Consumer spending signals
- Platform policy or antitrust developments

### Theme 3: Cloud and Enterprise Software

Representative names: MSFT, AMZN, GOOGL

Key events to monitor:
- Cloud revenue growth and margin trends
- Enterprise AI adoption commentary
- Capex efficiency and infrastructure utilization
- Large-customer demand commentary in filings

### Theme 4: EV and Industrial AI

Representative names: TSLA, NVDA

Key events to monitor:
- EV deliveries and pricing changes
- Autonomy and robotics milestones
- Semiconductor demand tied to automotive and edge AI
- Energy storage and clean-energy deployment commentary

## Benchmark

| Benchmark | Ticker | Purpose |
| --- | --- | --- |
| S&P 500 ETF | SPY | Default broad-market benchmark for risk and relative performance |

## Notes

1. The project treats the Magnificent 7 as the default research universe, but all services should remain reusable for other U.S. tickers.
2. SEC EDGAR is the primary filing source. Outputs should prefer evidence grounded in official filings when available.
3. Market data should come from yfinance-compatible local caches or live yfinance fetches.
