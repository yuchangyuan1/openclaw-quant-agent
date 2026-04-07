# Critic Ethics Review Playbook

1. Use the `critic-review` skill.
2. Apply the 5-point ethics checklist in this order:
   a. Are all key claims supported by evidence? (`claims_supported_by_evidence`)
   b. Is data freshness explicitly stated? (`data_freshness_explicit`)
   c. Is there any conflict between analysis and risk outputs? (`no_analysis_risk_conflict`)
   d. Does the output overstate certainty or use direct investment advice language? (`no_overstatement`)
   e. Is the action boundary clearly marked in the output? (`action_boundary_appropriate`)
3. Return the checklist result before any commentary.
4. If any checklist item fails, set `recommended_action_boundary` to `informational_only`.
5. If all items pass but warnings exist, set `recommended_action_boundary` to `analysis_only`.
6. Always return `overstatement_detected` as a boolean field.
7. Keep all findings auditable — cite specific content snippets when flagging failures.
8. This review is mandatory for all report and recommendation outputs. It cannot be skipped.
