# critic-review

Purpose:

- call the Critic service as the mandatory ethics gate

Focus:

- evidence coverage
- data freshness
- consistency between analysis and risk outputs
- overstatement detection
- action boundary appropriateness

Ethics checklist (5 items):

1. `claims_supported_by_evidence` — key claims backed by evidence
2. `data_freshness_explicit` — data date is stated in the output
3. `no_analysis_risk_conflict` — no conflict between quant and risk conclusions
4. `no_overstatement` — no direct investment advice or certainty overstatement
5. `action_boundary_appropriate` — action boundary marker is present

Output:

- `status`: PASS / PASS_WITH_WARNINGS / FAIL
- `warnings`: list of warning messages
- `errors`: list of failure messages
- `ethics_checklist`: dict with the 5 checklist item results (bool)
- `overstatement_detected`: bool
- `recommended_action_boundary`: "informational_only" or "analysis_only"
