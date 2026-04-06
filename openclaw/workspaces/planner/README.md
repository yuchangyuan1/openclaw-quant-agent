# Planner Workspace

This workspace owns top-level intent routing and orchestration.

Use it for:

- document QA
- quant query routing
- risk query routing
- daily report routing
- weekly report routing
- run log inspection
- alert summary and replay workflows

Do not use it for:

- direct low-level market calculations
- direct risk computation
- raw scraping logic

Those belong to service-backed skills.

Default collaboration patterns:

- `DOC_QA`: `Planner -> Knowledge`
- `QUANT_QUERY`: `Planner -> Quant`
- `RISK_QUERY`: `Planner -> Risk`
- `DAILY_REPORT`: `Planner -> Knowledge + Quant + Risk -> Report -> Critic`
- `WEEKLY_REPORT`: `Planner -> Knowledge + Quant + Risk -> Report -> Critic`
