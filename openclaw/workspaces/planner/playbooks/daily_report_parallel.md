# Daily Report Parallel Playbook

1. Start from the planner HTTP service or a scheduled planner session.
2. Use `sessions_spawn` to run these collaborators in parallel:
   - `knowledge` for the evidence pack
   - `quant` for market and factor outputs
   - `risk` for exposure and drawdown checks
3. When all three finish, hand their outputs to `report`.
4. Send the drafted report to `critic`.
5. Only after critic review should planner deliver the final summary.
6. If one parallel branch fails, report the degraded branch explicitly instead of pretending the whole pipeline succeeded.
