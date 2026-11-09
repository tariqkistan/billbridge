# Scoping note: Karoo Mobile bill-dispute agent

> Karoo Mobile is fictional. This is a pilot rehearsal: every customer-side system is a simulator in `legacy_sim/`.

## Problem
Billing queries are the largest contact-centre queue. Most are "why did my bill go up?" and "did my payment land?". Agents answer them by checking three or four legacy screens. Average handle time is high, and the answers are mechanical.

## Users
- **Customers:** postpaid subscribers asking about their latest invoice or a recent payment.
- **Contact-centre agents:** they receive escalations and need the full context so they do not re-ask.
- **Billing ops / IT:** they own the legacy systems and care that the agent does not add load or leak data.

## In scope for the pilot
| Capability | Tool |
| --- | --- |
| Verify identity (mobile number + ID last 4 + date of birth) | `verify_identity` |
| Explain the latest or a named invoice and what changed since the previous month | `get_invoice_breakdown` |
| Report recent payments and whether they have settled | `get_payment_status` |
| Hand over to a human with a summary and ticket | `escalate_to_human` |

## Out of scope (explicitly)
- Credits, refunds, waivers or any write to billing. The agent explains; humans decide.
- Plan changes, porting, SIM swaps (high fraud risk).
- Prepaid, business accounts, multi-account customers.
- Voice channel.

## Success metrics
| Metric | Pilot target | Source |
| --- | --- | --- |
| Containment rate (no escalation) | >= 60% of verified billing sessions | `scripts/report.py` |
| Grounding failures | < 1% of turns; every one reviewed | event log `grounding_fail` |
| Scenario suite pass rate | >= 90% before any prompt or model change ships | CI eval gate |
| Escalations with usable summary | >= 95% (human QA sample) | ticket review |
| Data leaks to unverified callers | 0 | scenario suite + QA |
| Customer resolution (CSAT/re-contact in 7 days) | tracked, no target in pilot | contact-centre data |

Containment is not resolution: a contained session can still be an unhappy customer, so re-contact rate is tracked alongside it.

## Integrations discovered
| System | Interface | Owner | Notes |
| --- | --- | --- | --- |
| CRM | JSON lookup by MSISDN | IT | Legacy keys, duplicate INACTIVE records, DD/MM/YYYY dates |
| Billing | Nightly CSV export endpoint | Billing ops | `;`-delimited, `R312,50` decimal commas, category codes |
| Payments | JSON | Finance | Amounts as strings, single-letter statuses |
| Ticketing | REST | Contact centre | Requires `Idempotency-Key` |
