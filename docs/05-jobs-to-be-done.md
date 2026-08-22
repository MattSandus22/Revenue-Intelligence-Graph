# 5. Jobs-to-be-Done

Format: *When [situation], I want to [motivation], so I can [outcome].* Each JTBD maps to modules (see doc 6) and screens (doc 14).

## 5.1 Retention jobs (wedge)

| # | Persona | Job | Module / Screen |
|---|---|---|---|
| J1 | CSM | When I start my day, I want a ranked list of which of my accounts need attention and why, so I spend time where ARR is actually at risk | Workbench, Signals Engine |
| J2 | CSM | When an account shows risk, I want all evidence in one timeline, so I can diagnose in minutes not hours | Account 360, Evidence Timeline |
| J3 | CSM | When I prepare for a renewal/QBR, I want a source-backed brief and plan draft, so prep takes 30 minutes not a day | QBR prep, Account Plan generator |
| J4 | CSM | When I disagree with an alert, I want to dismiss it with a reason and have the system learn, so alerts stay worth reading | Feedback capture |
| J5 | VP CS | When a renewal quarter starts, I want to see every renewal's risk, plan status, and owner coverage, so nothing reaches me late | Renewal Command Center |
| J6 | VP CS | When a strategic account degrades, I want automatic escalation with evidence, so I can deploy execs early | Escalation rules, Evidence Cards |
| J7 | VP CS | When I forecast renewals, I want a risk-adjusted number with calibration history, so I can defend it to the CRO | Risk-adjusted forecast |
| J8 | RevOps | When leadership asks "why did we churn X?", I want the full signal/action/outcome history, so postmortems are factual | Risk lifecycle, Outcome review |

## 5.2 Expansion jobs

| # | Persona | Job | Module |
|---|---|---|---|
| J9 | CSM/AE | When an account approaches capacity or adds teams, I want a credible expansion suggestion with evidence and timing, so I raise it at the right moment | Expansion Intelligence |
| J10 | VP Sales | When planning pipeline, I want expansion candidates ranked by propensity and unblocked-by-risk status, so AEs work real opportunities | Expansion pipeline (draft, approval-gated) |

## 5.3 Forecast-reliability jobs

| # | Persona | Job | Module |
|---|---|---|---|
| J11 | Sales Manager | When a rep commits a deal, I want evidence-vs-category inconsistencies flagged, so I inspect the right deals | Forecast Reliability |
| J12 | VP Sales | When I roll up forecast, I want hygiene and calibration context, so my number isn't fiction | Forecast Reliability |

## 5.4 Data-trust jobs

| # | Persona | Job | Module |
|---|---|---|---|
| J13 | RevOps | When data breaks or drifts, I want to know before users see wrong insights, so trust survives | Data Quality Command Center |
| J14 | RevOps | When two systems disagree on ACV/owner/renewal date, I want conflict surfaced with source-of-truth rules, so there is one answer | Conflict resolution |
| J15 | Data admin | When a connector degrades, I want alerting, impact scoping ("these 40 accounts stale"), and replay, so recovery is routine | Integration Health |

## 5.5 Executive jobs

| # | Persona | Job | Module |
|---|---|---|---|
| J16 | CRO/CEO | Every week, I want a brief of material risk/opportunity changes with linked evidence, so I trust and act on it | Weekly Executive Brief |
| J17 | CRO | When board prep comes, I want retention KPIs whose lineage I can show, so numbers survive scrutiny | Reporting + lineage |

## 5.6 Investigation jobs

| # | Persona | Job | Module |
|---|---|---|---|
| J18 | Any business user | When I have a question ("why is Acme at risk?", "which commit deals have no next step?"), I want an evidence-cited answer over data I'm allowed to see, so I skip the BI queue | Investigation Copilot |

## 5.7 Administration jobs

| # | Persona | Job | Module |
|---|---|---|---|
| J19 | Model admin | When our segments behave differently, I want segment-specific score weights with backtest preview, so scores fit our business | Model/Score Config |
| J20 | Security admin | When procurement/audit asks, I want access logs, AI governance settings, and deletion proof, so reviews pass quickly | Security & Audit Admin |

**Prioritization:** MVP must nail J1–J8, J13–J16, J18 (read-only-ish investigation), J19 (basic weights), J20 (basic audit). J9–J12 are V1/V2.
