# Pilot plan (6 weeks)

| Week | Goal | Exit criteria |
| --- | --- | --- |
| 1: Discovery | Confirm scope, assumptions log, access to sandbox systems, sample exports | Assumptions A1–A10 answered; sandbox credentials; 50 anonymised real transcripts |
| 2: Integrate | Point adapters at sandbox systems, extend the simulator with any new quirks found | Adapter tests pass against recorded sandbox responses |
| 3: Evaluate | Grow the scenario suite from real transcripts (target 40+ scenarios) | >= 90% pass rate, zero leak scenarios failing |
| 4: Shadow | Agent drafts answers for human agents, who send or edit them | Edit rate and grounding failures measured on live traffic |
| 5: Limited live | 5–10% of billing chats, business hours, kill switch ready | Containment, escalations and grounding failures within targets for 5 days |
| 6: Review & handover | Metrics review with client, runbook walkthrough, go/no-go for scale-up | Signed-off handover runbook; owners named for every alert |

## Risks
| Risk | Mitigation |
| --- | --- |
| Model invents or miscalculates an amount | Arithmetic in code; grounding check fails closed to a human |
| Social engineering past verification | Gate in code; account tools take no account id; lockout |
| Legacy systems slow or down | Retries with backoff; `backend_unavailable` → escalation |
| Export format changes silently | Parsers raise `DataQualityError`; alert on rate of data-quality errors |
| Prompt change regresses behaviour | CI scenario gate on every change to `main` |
