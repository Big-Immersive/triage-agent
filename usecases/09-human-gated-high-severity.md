# Human approval for high-severity and low-confidence tickets

**For:** Engineering leads

## The problem

Fully autonomous ticket creation is risky for critical/billing issues, but reviewing everything defeats the purpose.

## How the agents handle it

The gate lives inside `create_ticket`, not in the prompt: if severity ≥ the configured floor or the investigator's confidence < the threshold, the run pauses. The approval card shows agent, action, reason, confidence, evidence. APPROVE / MODIFY (change severity) / REJECT. The run resumes with the decision; a parked run frees the queue so other tasks continue. Approvals survive server restarts.

## Example outcomes

- FB-014 double charge → paused as 'high' → reviewer modifies to 'critical' → ticket created as critical with approved_by=human.

## What to configure

- approval.config: severity floor and minimum confidence
- Slack/Discord/Email notifications on approval.requested

## Value

Autonomy where it is safe, a human exactly where it matters, with an audit trail.
