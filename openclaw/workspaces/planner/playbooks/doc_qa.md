# DOC_QA Playbook

1. Route the incoming query through the planner HTTP service.
2. Prefer evidence-backed answers from the RAG / Knowledge pipeline.
3. Include sources, data date, and critic status.
4. If the planner service is unavailable, report that the local planner path is down.
5. Do not silently switch to unrelated web search without stating the fallback.
