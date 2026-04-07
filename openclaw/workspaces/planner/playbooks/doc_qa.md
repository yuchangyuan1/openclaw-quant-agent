# DOC_QA Playbook

1. Route the incoming query through the planner HTTP service.
2. Prefer evidence-backed answers from the RAG / Knowledge pipeline.
3. Include sources, data date, and critic status.
4. Always include `action_boundary` and `human_approval_required` in the reply.
5. If the planner service is unavailable, report that the local planner path is down.
6. Do not silently switch to unrelated web search without stating the fallback.
