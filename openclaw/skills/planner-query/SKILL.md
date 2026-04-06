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

Use this skill whenever the caller wants the canonical planner execution path.
