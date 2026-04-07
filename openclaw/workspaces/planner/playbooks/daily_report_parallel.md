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
7. Read `action_boundary` and `human_approval_required` from the final planner response.
8. If `human_approval_required` is true, prefix the Feishu summary with: 【⚠ 需要人工审批后方可执行任何操作】
9. Always include `action_boundary`, `human_approval_required`, and `accountability_trail` in the delivered response.
