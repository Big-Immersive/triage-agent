# Use cases

Twenty ways to use the triage agents platform, from the shipped bug-triage template to custom workflows. Each file describes the scenario, how the agents handle it, example outcomes, and what to configure.

| # | Use case | For |
|---|---|---|
| 01 | [App / Play Store review triage](01-app-store-review-triage.md) | Product team of a mobile game or app |
| 02 | [Discord community bug channel](02-discord-community-reports.md) | Community managers / live-ops |
| 03 | [Support email → engineering tickets](03-support-email-inbox.md) | Support team + engineering |
| 04 | [In-app feedback form](04-in-app-feedback-form.md) | Mobile / web product teams |
| 05 | [Release-day incident: many reports, one bug](05-release-incident-dedup.md) | On-call engineers |
| 06 | [Regression detection](06-regression-detection.md) | QA / release managers |
| 07 | [Vague report → clarification instead of a bad ticket](07-vague-report-clarification.md) | Support / community |
| 08 | [Filtering praise, spam, feature requests and support questions](08-noise-filtering.md) | Anyone drowning in feedback |
| 09 | [Human approval for high-severity and low-confidence tickets](09-human-gated-high-severity.md) | Engineering leads |
| 10 | [Corroborating reports with crash telemetry](10-crash-telemetry-corroboration.md) | Engineering |
| 11 | [Non-English feedback](11-multilingual-feedback.md) | Global products |
| 12 | [Routing to the owning team via CODEOWNERS](12-ownership-routing.md) | Engineering managers |
| 13 | [Release-aware urgency](13-release-urgency.md) | Release managers |
| 14 | [Mirroring tickets to GitHub / Jira / Linear](14-tracker-mirroring.md) | Teams living in their tracker |
| 15 | [Notifying the team where they are](15-team-notifications.md) | Everyone |
| 16 | [Fully hands-off pipeline via the intake endpoint](16-hands-off-pipeline.md) | Ops / automation owners |
| 17 | [Backfilling months of historical feedback](17-historical-backfill.md) | Product analytics |
| 18 | [Agency / platform team with many isolated products](18-agency-multi-client.md) | Agencies, platform teams, multi-brand companies |
| 19 | [Knowledge-grounded triage with your own docs](19-knowledge-grounded-triage.md) | Teams with architecture and product docs |
| 20 | [Designing your own agent workflow](20-custom-agent-workflows.md) | Anyone with a different triage shape |

## Complex, end-to-end scenarios (`complex/`)

Long-form walkthroughs with concrete data, the agents' actual tool sequences, edge cases and what is still manual.

| # | Scenario |
|---|---|
| 1 | [Release-day regression storm across four channels](complex/01-release-regression-storm.md) |
| 2 | [Enterprise support desk with billing disputes and SLAs](complex/02-enterprise-support-desk.md) |
| 3 | [Agency running triage for five isolated clients](complex/03-agency-multi-client-operations.md) |
| 4 | [QA bug bash: 300 internal reports in an afternoon](complex/04-qa-bug-bash-300-reports.md) |
| 5 | [Security vulnerability intake with a custom two-agent workflow](complex/05-security-vulnerability-intake.md) |
| 6 | [Operating at scale: three backend replicas on Railway](complex/06-scaling-operations-on-railway.md) |
| 7 | [Mining 12 months of reviews and iterating with an eval set](complex/07-historical-mining-and-model-iteration.md) |

See also: `docs/CAPABILITIES.md` (everything the platform does today) and `docs/FUTURE_RESEARCH.md` (what to add next).
