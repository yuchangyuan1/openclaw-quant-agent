# report-build

Purpose:

- call the Report service to render daily or weekly reports

Inputs:

- report type
- evidence payload
- quant payload
- risk payload
- critic status
- ethics_section (evidence_status, data_freshness, conflict_detected, human_approval_required, action_boundary)

Output:

- report content (includes "审查与合规" section)
- archive path
- summary snippet
- `action_boundary`: "informational_only" | "analysis_only" | "requires_human_approval"
- `human_approval_required`: bool
