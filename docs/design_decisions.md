# Design decisions and trade-offs

| Decision | Alternative considered | Why this way |
| --- | --- | --- |
| Hand-written ~40-line tool loop | LangChain / agent framework | Every line is explainable; no hidden retries or prompt injection points; easy to test with a scripted fake model |
| Verification gate inside each tool | Prompt rule only | A prompt can be talked around; a check in code cannot. The prompt is the soft layer, the gate is the hard layer |
| Account tools take no account id | Pass account id from the model | Removes the target for "show me account X" injections; only `verify_identity` sets `session.customer` |
| Same response for unknown number and wrong details | Helpful "number not found" | Prevents using the agent to enumerate customers |
| Money as integer cents | Floats / Decimal | Integers add exactly; JSON-friendly; matches how ledgers reconcile |
| Month-on-month changes computed in code | Let the model subtract | LLMs are unreliable at arithmetic; the model only narrates numbers it was handed |
| Grounding check fails closed | Log and allow | A wrong amount on a bill is worse than a handover |
| Three error classes (transient, permanent, data quality) | Catch-all exception | The class decides behaviour: retry, fail fast, or escalate |
| Parser refuses ambiguous amounts | Best-guess parsing | Guessing silently corrupts bills; ambiguity is a discovery question |
| Idempotency key per escalation, one ticket per session | Trust the client not to retry | Retries are certain under flaky networks |
| In-memory session store | Redis | Fine for the pilot rehearsal; named as a production gap |
| SQLite event log with names and outcomes only | Full transcript logging | Keeps personal data out of logs by construction; enough for metrics |
| Simulator outside `src/` | Mock inside the package | Mirrors a real engagement: the customer's systems are not your product |
| Scenario suite with a real model gated in CI; deterministic tests with a scripted model | Only one of the two | Deterministic tests prove the code; the scenario suite proves the model + prompt |
| `temperature=0` | Default sampling | Repeatable scenario runs and steadier answers |
| `except TypeError` for bad tool arguments | Pydantic model per tool | Simple first version; would move to per-tool Pydantic validation so real bugs surface |
