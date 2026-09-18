# Complex use case 2 — Enterprise support desk with billing disputes and SLAs

**Context.** A B2B SaaS (invoicing product, EU customers) runs support in Zendesk. Tier-1 agents escalate "looks like a bug" tickets to engineering. Billing disputes must never be filed as ordinary bugs; anything touching invoices or payments needs a human decision within 4 business hours (contractual SLA). Reports are in English, German and French and often contain PII (names, invoice numbers, card last-4).

**Goal.** Zendesk escalations become deduplicated engineering tickets in Linear with the owning squad, billing issues are gated to a human with an email + Slack alert, tier-1 gets a reply draft in the customer's language, and no PII leaves the project.

## Setup

- **Project `invoicing-support`.** Instructions: product glossary (invoice run, dunning, SEPA mandate…), "any billing, payment, VAT or invoice-amount issue is at least high severity and must cite the invoice id", "never include card numbers in tickets; reference the Zendesk ticket instead".
- **Agents (edited from the template):**
  - `intake` — additional instruction: "extract `zendesk_id`, `plan`, `region` from Metadata into the summary; language codes en/de/fr".
  - `investigator` — tools + `search_knowledge` (see below); instruction: "search the knowledge base for the feature before searching the tracker".
  - `triage` — unchanged; CODEOWNERS maps `billing`→squad-payments, `invoicing`→squad-core, `pdf`→squad-docs.
  - `writer` — unchanged (gate lives in `create_ticket`).
- **Knowledge:** Linear export as `tickets.json` (id prefix `INV-`; the runtime picks the prefix up automatically, so new tickets become `INV-…`), `releases.json` (weekly releases, user share by region), product docs (PDF/Markdown) for `search_knowledge`, no crash log (`query_crashes` answers "No crash log is connected" and the agents move on).
- **approval.config:** floor = **medium** (this team wants to see medium+), min confidence 0.75.
- **Integrations:** Linear (team INV), Email (Postmark SMTP → `oncall-payments@…`), Slack `#support-escalations`, Webhook → the SLA tracker (`events: approval.requested,approval.resolved`).
- **Intake:** Zendesk trigger "tag = escalate-eng" → HTTP target `POST /api/intake/{project}`:

```json
{"items":[{"id":"ZD-48812","source":"zendesk","author":"agent.k.meyer","received_at":"2026-09-18T08:12:00Z",
  "text":"Kunde meldet: Rechnung R-2026-0912 wurde doppelt abgebucht (SEPA), Betrag 480,00 €. Kunde ist auf Plan Business, Region DE.",
  "metadata":{"zendesk_id":"48812","plan":"business","region":"DE","app_version":"2026.37"}}]}
```

## Flow for the German double-debit case

1. `intake`: `category=bug`, `language=de`, summary *"Invoice R-2026-0912 debited twice via SEPA (€480), Business plan, DE"*, `app_version=2026.37`.
2. `investigator`: `search_knowledge("SEPA double debit dunning retry")` → passage from `payments-runbook.md`: *"a failed SEPA collection is retried after 3 days; a manual retry from the admin panel while the automatic retry is pending produces a double collection"*. `search_recent_reports` → none. `search_tickets("double SEPA debit")` → `INV-203 score=0.71 STRONG, status=open`. Verdict **duplicate of INV-203**, confidence 0.82 → `writer` → `comment_on_ticket("INV-203", "+1 ZD-48812 … R-2026-0912 … DE")`. No gate (duplicates never gate). Linear is not touched (comments are local artifacts; roadmap: mirror comments).
3. Slack: nothing (only approvals, tickets, failures post). The SLA webhook receives no approval event → the SLA clock is not started for a duplicate — correct.

## Flow for a new VAT-rounding bug (French)

1. `intake`: bug, `language=fr`, summary *"VAT total on invoice differs by €0.01 from line-item sum for FR customers with 20% VAT"*.
2. `investigator`: knowledge → *"VAT is computed per line and summed; rounding mode is HALF_EVEN"*; tracker → no STRONG match; verdict **new**, confidence **0.68** (below 0.75).
3. `triage`: `medium` (cosmetic on the document but affects accounting), `component=invoicing` → squad-core.
4. `writer` → `create_ticket` → **gate** (severity medium ≥ floor *and* confidence < 0.75; both reasons listed). Email to `oncall-payments@…` and Slack post with the deep link; the SLA webhook receives `approval.requested` with `requested_at` and starts the 4h clock.
5. Reviewer opens the approval card: evidence cites the runbook passage; they **MODIFY** to `high` ("accounting impact"). The run resumes, files `INV-241` (high, invoicing, approved_by=human) → Linear issue `INV-241` priority High with the markdown → `approval.resolved` webhook stops the SLA clock (1h12m).
6. Memory: `DECISIONS: Reviewer overrode the proposed severity on RUN_… to high.` — next time the triage agent's instructions can be tightened, or (roadmap) these overrides become few-shot examples.

## PII handling as configured

- Card data never reaches tickets: the project instructions forbid it and tier-1 already redacts in Zendesk; the ticket references `ZD-48812`.
- Everything the agents see stays inside the project (isolation is enforced in the API and the vector store); the global dashboard only shows headlines like `RUN complete: new_ticket INV-241`.
- Integration secrets (Linear key, SMTP password, webhook secret) are encrypted at rest and masked in the UI.
- Roadmap: a redaction step in `intake` (regex + model) for emails/IBANs before anything is embedded.

## Edge cases exercised

| Situation | Behaviour |
|---|---|
| Zendesk sends the same ticket twice (trigger re-fires) | `id` is unique per project → second POST is `skipped`, no duplicate run |
| Tier-1 escalates a "how do I export to DATEV?" question | `support_question` → dropped with reason; visible under tickets › DROPPED for the KB team |
| Linear is down when a ticket is created | Ticket still created locally; integration flips to ● ERROR with the message; activity shows `LINEAR delivery failed: …`; TEST after recovery; roadmap: retry queue |
| Reviewer is out; approval sits for a day | Run stays `waiting_approval`, other tasks continue; heartbeat keeps it alive; the SLA webhook consumer escalates |
| Backend redeploy during the wait | Run marked interrupted, approval pending; decision later re-runs the task with it carried over |

## Metrics the team watches

- approvals › RESOLVED: time from `requested_at` to `resolved_at` (SLA) — exported via the webhook.
- settings › usage: cost per project per month (Business plan support ≈ $40/month at 2,000 escalations).
- tickets: ratio of tickets to +1 comments (dedup effectiveness), share of `approved_by=human` overrides.
