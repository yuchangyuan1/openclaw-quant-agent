# Ethics Transformation Plan

## 1. Objective

This document records the ethics-oriented transformation that has already been applied to the project.

The system is no longer framed as a pure quant workflow. It is now an ethics-aware multi-agent decision support system with:

- evidence grounding
- bounded action boundaries
- critic review
- accountability trails
- human approval signaling

## 2. Architecture-Level Changes

The transformation kept the original service-oriented architecture and changed the behavior contract around outputs.

Retained:

- OpenClaw control plane
- deterministic FastAPI services
- Postgres + Lightweight Graph + Chroma
- planner / knowledge / quant / risk / report / critic split

Changed:

- every major planner response now carries ethics metadata
- critic review became mandatory for report delivery
- action boundaries are explicitly computed and surfaced
- audit output is structured around accountability rather than raw execution only

## 3. Implemented Ethics Contracts

### Response-Level Fields

Current planner-facing ethics fields:

- `evidence_status`
- `data_freshness`
- `risk_status`
- `critic_status`
- `conflict_detected`
- `action_boundary`
- `human_approval_required`
- `accountability_trail`

### Critic Checklist

The critic service evaluates:

1. evidence sufficiency
2. freshness transparency
3. analysis and risk consistency
4. overstatement language
5. action-boundary appropriateness

### Action Boundary Policy

Outputs are constrained to:

- `informational_only`
- `analysis_only`
- `requires_human_approval`

The system is allowed to become more restrictive, not less restrictive, after critic review.

## 4. Current Project Context

The current repository version applies this ethics layer to the US-market implementation:

- market data: yfinance
- filing source: SEC EDGAR
- default universe: Magnificent 7
- benchmark: SPY

## 5. Validation

The transformed project currently passes:

```bash
python -m compileall services scripts tests
pytest -q -p no:cacheprovider tests
```

Current result:

- `78 passed`

## 6. Remaining Optional Enhancements

Potential future ethics-oriented improvements:

1. more explicit disagreement presentation between quant and risk outputs
2. stronger approval workflows for sensitive report types
3. deeper OpenClaw runtime-native subagent execution with the same ethics contract
