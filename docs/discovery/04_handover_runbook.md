# Handover runbook

## What runs
| Component | Command | Port |
| --- | --- | --- |
| Agent API | `uvicorn billbridge.api:app` | 8000 |
| Legacy simulator (demo only) | `uvicorn legacy_sim.app:app` | 9000 |
| Metrics report | `python -m scripts.report --since-hours 24` | – |
| Scenario suite | `python -m scripts.run_scenarios --min-pass-rate 0.9` | – |

Configuration is environment variables only (see `.env.example`). No secrets in the repo.

## Daily checks
Run `python -m scripts.report --since-hours 24` and compare with the targets in the scoping note.

| Signal | Healthy | Investigate when |
| --- | --- | --- |
| Containment rate | >= 60% | Drops more than 10 points day on day |
| `grounding_failures` | ~0 | Any non-zero: read the session's tool trace |
| `backend_error:*` rate per tool | < 2% | > 5% for an hour: check the legacy system's status |
| p95 latency per tool | < 2 s | > 5 s: backend slow, retries stacking |
| Escalation reason `verification_locked` | low | Spike can mean an attack on verification |

## Incidents
| Symptom | Likely cause | Action |
| --- | --- | --- |
| Every session escalates with `backend_unavailable` | CRM/billing down | Confirm with system owner; agent is failing safe, no action needed beyond comms |
| Sudden `DataQualityError` outcomes | Export format changed | Capture a sample, add it to the simulator and adapter tests, fix the parser |
| Duplicate tickets | Ticketing ignoring `Idempotency-Key` | Raise with ticketing owner; check one-ticket-per-session logic |
| Grounding failures after a deploy | Prompt or model change | Roll back; run the scenario suite; add the failing case as a scenario |

## Changing the agent safely
1. Add or update a scenario in `scenarios/scenarios.yaml` that captures the desired behaviour.
2. Change the prompt, tools or adapters.
3. `pytest -m "not eval"`, then `python -m scripts.run_scenarios`.
4. Merge only when CI is green, including the scenario eval gate on `main`.

## Known gaps before production
- Sessions live in memory (lost on restart, single instance only). Move to Redis with expiry.
- No authentication on `/chat`; it must sit behind the channel platform's auth.
- Event log is local SQLite; ship events to the client's log platform.
- Grounding check only covers amounts written as `R123,45`; amounts without cents are not checked.
