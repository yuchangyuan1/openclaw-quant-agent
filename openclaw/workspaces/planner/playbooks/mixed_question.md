# Mixed Question Playbook

1. Route the request through the planner HTTP service first.
2. If the question spans documents, quant, and risk, use `sessions_spawn` to run:
   - `knowledge`
   - `quant`
   - `risk`
3. Wait for the parallel collaborators to finish.
4. Merge the three outputs into one user-facing reply.
5. Preserve source timestamps, evidence counts, and warnings.
6. Do not let planner answer a mixed question from prompt-only reasoning when delegated paths are available.
