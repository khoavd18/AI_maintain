# Maintenance Copilot Safety Boundary

The Copilot is read-only decision support. It does not execute shell/SQL/tools, control equipment, create or close tickets/work orders, mutate inventory or maintenance records, claim work was completed, or provide a definite real-time diagnosis.

Deterministic checks cover user input, retrieved chunks, allow-listed asset context, and LLM output. They reject prompt overrides, prompt/secret requests, embedded tool calls, shell commands, state-changing SQL-like directives, automated business-state requests, unsupported equipment, non-maintenance questions, and selected-asset mismatch. Unsafe retrieved chunks are removed; if no safe evidence remains, the response is a zero-source fallback.

Only bounded asset identity/location, risk-prioritization, and recent anomaly fields reach generation. Risk and anomaly values are labeled as supporting batch context, not a failure probability or sensor diagnosis. Reporter contact, credentials, cookies, attachment bodies/paths, arbitrary serialized models, comments, and transactional ledgers are excluded.

Multi-turn requests accept a structured summary rather than raw history. The summary is length-limited and screened for unsafe instructions; old equipment/failure context is used only when the new question is an explicit follow-up and cannot override a newly named asset type.

Human facility managers and technicians remain responsible for field inspection, PPE and isolation decisions, manufacturer instructions, maintenance execution, ticket resolution, and final decisions.
