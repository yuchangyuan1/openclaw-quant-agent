# planner-query

Purpose:

- call the planner HTTP entry point
- standardize request and response handling

Default command:

```powershell
python scripts/call_planner_service.py "<user_message>"
```

Expected output:

- `reply_markdown`
- `intent`
- route-specific payload fields
- `evidence_status`: "SUFFICIENT" | "PARTIAL" | "INSUFFICIENT" | "NONE"
- `data_freshness`: "FRESH" | "ACCEPTABLE" | "STALE" | "UNKNOWN"
- `risk_status`: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN"
- `conflict_detected`: bool
- `human_approval_required`: bool
- `action_boundary`: "informational_only" | "analysis_only" | "requires_human_approval"
- `accountability_trail`: structured dict with participating agents, evidence count, risk gate result, critic result

Use this skill whenever the caller wants the canonical planner execution path.
