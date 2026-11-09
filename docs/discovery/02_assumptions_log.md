# Assumptions log

Each assumption is a question we would confirm with the client during discovery week. Status in a real engagement moves from **open** to **confirmed** or **changed**.

| # | Assumption | Why it matters | How the build handles it | Status |
| --- | --- | --- | --- | --- |
| A1 | Billing amounts use a decimal comma (`R312,50`) and a space for thousands | Misparsing changes the amount 100-fold | `parse_money_to_cents` handles comma or dot decimals and refuses ambiguous input | open |
| A2 | A value like `1,234` never appears in exports | It could be R1 234 or R1,234 | Raises `DataQualityError` and escalates instead of guessing | open |
| A3 | Exactly one ACTIVE CRM record per MSISDN | Two ACTIVE records means we cannot know whose bill to show | Picks the single ACTIVE record; two ACTIVE records is a data-quality error | open |
| A4 | Mobile number + ID last 4 + date of birth is an acceptable verification level for read-only billing info | It is the security boundary | Gate enforced in code; lock after 3 failures | open (needs client security sign-off) |
| A5 | Unknown billing category codes are rare | New codes would be mislabelled | Mapped to `other`, still counted in totals | open |
| A6 | Payment status codes are only S, P, F | A new code could be misreported as settled | Unknown status raises `DataQualityError` | open |
| A7 | Invoices are monthly, period `YYYYMM` | The month-on-month comparison assumes it | Period start/end derived from `PERIOD` | open |
| A8 | Ticketing honours `Idempotency-Key` | Retried POSTs could duplicate tickets | Stable key per session + reason; one ticket per session | open |
| A9 | Backends tolerate 3 attempts with backoff | Retries add load during incidents | Exponential backoff with jitter, honours `Retry-After`, no 4xx retries | open |
| A10 | Conversation text may contain personal data | POPIA obligations | Event log stores tool names and outcomes only, never message text | open |
