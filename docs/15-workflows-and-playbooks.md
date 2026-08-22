# 15. Detailed Workflows and Playbooks

Format per workflow: **Trigger → Inputs → System steps → AI steps → Approvals → Notifications → Permissions → Audit → Failure paths → Success metrics.** Shared rule: every state change writes an audit event; every external effect is approval-gated; every notification respects per-user channel preferences.

---

### WF-1. Renewal risk detected
- **Trigger:** risk score crosses tenant threshold (default ≥70) or a critical signal fires on an account with renewal ≤ 180d.
- **Inputs:** score + components, active signals, account profile, owner, playbook registry.
- **System:** compose insight (bundle contributing signals) → build evidence card → verify citations → rank urgency → create risk in `detected` → route (WF-2).
- **AI:** insight narrative generation (cited); recommended actions (D.10). LLM-derived contributing signals marked with review state.
- **Approvals:** none at detection (internal-only artifact).
- **Notifications:** owner Slack DM + workbench badge (critical: immediate; high: within digest SLA).
- **Permissions:** visible to users with account scope.
- **Audit:** `insight.created` with inputs hash.
- **Failure:** verification fails → insight held in `needs_review` queue, ops alert; owner unset → route to team lead + data-quality issue (missing owner).
- **Metrics:** detection-to-notification latency (<5 min); alert acceptance rate.

### WF-2. Risk triage and ownership assignment
- **Trigger:** risk in `detected`. **Inputs:** risk, evidence card, workload data.
- **System:** owner reviews evidence → accept (→`accepted`, becomes actionable) or dismiss (reason code mandatory) → optional reassign (workload view assists leaders) → SLA timers start (triage SLA default 48h; breach → escalation per rules).
- **AI:** none (human judgment step by design).
- **Approvals:** dismissal of critical risks on strategic accounts requires leader confirmation (configurable).
- **Notifications:** assignment pings; SLA-breach alerts to leader.
- **Permissions:** triage = owner/leader with account scope. **Audit:** state transitions with actor + reason.
- **Failure:** untriaged past SLA → auto-escalate; disputed ownership → leader queue.
- **Metrics:** time-to-triage; dismissal-reason distribution (feeds precision tracking).

### WF-3. CSM account investigation
- **Trigger:** CSM opens account from an alert or workbench. **Inputs:** Account 360, timeline, evidence.
- **System:** render profile with score explanations, conflict banners, data gaps; timeline filtered to risk-relevant events; "since last visit" markers.
- **AI:** account summary (D.6, cited); optional copilot questions (WF-18).
- **Approvals/Notifications:** none. **Permissions:** account scope; excerpt gating per field policy.
- **Audit:** sensitive-class views logged.
- **Failure:** stale data → banners with degraded confidence; missing sources → explicit gap statements.
- **Metrics:** investigation time (open → first action), evidence-card engagement.

### WF-4. Creating a mitigation plan
- **Trigger:** risk `accepted`. **Inputs:** risk evidence, playbook library, account plan.
- **System:** CSM selects playbook or custom plan → tasks created with owners/due dates → risk → `in_progress` → task sync (Slack/CRM/Jira per config, write-back preview approved once per rule or per instance) → progress tracked; stalled-task nudges.
- **AI:** playbook recommendation ranked by similarity to past successful mitigations (labeled suggestion).
- **Approvals:** external task sync per write-back rules; plan on strategic accounts optionally requires VP approval.
- **Notifications:** task assignments; weekly mitigation digest to leader.
- **Audit:** plan created/edited, tasks synced (payload hash). **Failure:** sync failure → retry/DLQ + in-app task remains source of truth.
- **Metrics:** % accepted risks with active mitigation ≤72h; task completion rate.

### WF-5. Executive escalation for a strategic account
- **Trigger:** escalation rule (doc 6 D) or manual escalate. **Inputs:** risk, tier, escalation policy, exec roster.
- **System:** escalation object with own owner + SLA → briefing pack auto-assembled (evidence card + history + asks) → exec acknowledges → outcomes tracked to closure.
- **AI:** one-page escalation brief (D.7-style, cited, review-gated because exec-facing).
- **Approvals:** brief reviewed by escalating leader before exec send.
- **Notifications:** exec (email+Slack), account team.
- **Permissions:** escalation visible to account team + exec chain. **Audit:** full escalation lifecycle.
- **Failure:** exec no-ack in SLA → reminder → CRO fallback contact.
- **Metrics:** escalation time-to-ack; save rate of escalated accounts.

### WF-6. Churn-risk signal from product usage decline
- **Trigger:** nightly aggregation → U1 detector.
- **Inputs:** usage_metric_daily, baselines, change calendar.
- **System:** compute baseline + deviation → FP guards (seasonality/holiday/denominator) → signal upsert (dedupe) → contributes to score; if crosses insight threshold → WF-1.
- **AI:** none (statistical); optional LLM contextualization when bundled ("decline concentrated in reporting module, admin users unaffected" — from structured breakdowns, cited).
- **Audit:** detector run versioned. **Failure:** usage feed stale >72h → signal evaluation suspended for account + data-quality issue (never fire on stale data).
- **Metrics:** signal precision (feedback), detection lead time vs. renewal.

### WF-7. Risk from a support escalation
- **Trigger:** ticket webhook: priority critical/escalated (S2/S5).
- **System:** resolve ticket→account → severity mapping → signal → strategic accounts: immediate insight + WF-5 evaluation; others: workbench routing → support-liaison task option.
- **AI:** thread summarization for evidence card (cited to messages); sentiment classification (D.1).
- **Notifications:** CSM DM within 5 min for critical.
- **Failure:** unmapped ticket org → orphaned-record DQ issue + resolution queue.
- **Metrics:** time from escalation to CSM awareness; resolved-before-renewal rate.

### WF-8. Risk from negative call sentiment + competitor mention
- **Trigger:** transcript ingested (Phase 2 connector or manual upload).
- **System:** chunk transcript → D.1 + D.3 extractions → schema/citation validation → signals (S4, C7) with spans → severity via context labels → review queue (LLM, high severity) → on human confirm: joins scores/insights and exec surfaces; unconfirmed stays CSM-visible labeled unreviewed.
- **AI:** as above; two-pass consistency.
- **Approvals:** reviewer = account owner or CS Ops (config).
- **Audit:** model runs + review decisions. **Failure:** validation failure → DLQ human queue; ambiguous speaker attribution → flagged in evidence.
- **Metrics:** extraction precision vs. human ratings; review turnaround.

### WF-9. Detecting expansion potential
- **Trigger:** U7/U8/U9/O6 signals.
- **System:** eligibility check (contract constraints, open risks) → expansion insight (`conditional` if risk open) → owner routing (AM/AE per territory rules) → accepted → expansion brief → optional draft opportunity.
- **AI:** evidence-backed expansion brief; timing recommendation (labeled).
- **Approvals:** **draft opportunity written to CRM only on explicit user approval** with field preview.
- **Metrics:** suggestion acceptance rate; influenced expansion ARR.

### WF-10. Preparing a QBR
- **Trigger:** QBR scheduled or R6 signal. **Inputs:** account history window, prior commitments, templates.
- **System:** prep pack assembly (scores/trends, usage highlights, support recap, commitments status, open risks, roadmap asks) → human edit → export (slides/PDF) → post-QBR: commitments captured (D.4 from notes/transcript, human-confirmed) into tracking.
- **AI:** D.8 composition — every claim cited; unverifiable items listed as "to verify."
- **Approvals:** CSM finalizes; customer-shared version excludes internal-only fields automatically (visibility classes).
- **Metrics:** prep time; commitment follow-through rate.

### WF-11. Weekly executive revenue-risk brief
- **Trigger:** cron (tenant-configured day) → draft. **Inputs:** metrics layer deltas, reviewed insights only.
- **System:** compute portfolio deltas → D.7 generation → claim verification (hard gate) → author review/edit → approve → distribute (email/Slack/PDF/slides) → engagement tracked.
- **Approvals:** designated approver required; unapproved briefs never send.
- **Audit:** generation, verification results, edits, approval, distribution list.
- **Failure:** verification blocks → excluded-claims appendix; metrics-layer failure → brief delayed with notice, never silently wrong.
- **Metrics:** on-time rate; exec engagement; zero unverified claims published (hard invariant).

### WF-12. Forecast inspection for a commit opportunity
- **Trigger:** O3 signal or manager opens inspection view.
- **System:** deal drawer with evidence-vs-category panel → manager action: coaching note, remediation task ("add dated next step"), or suggested category change → suggestion routed to rep → rep approves → write-back with preview → CRM updated.
- **AI:** next-step quality extraction (D.5); risk factors summary (cited).
- **Approvals:** category change = rep or manager per CRM permission model, always explicit.
- **Metrics:** commit accuracy trend; inspected-deal slip rate vs. uninspected.

### WF-13. Resolving a data-quality issue
- **Trigger:** DQ monitor emits issue (e.g., ARR mismatch).
- **System:** issue with impact statement + affected insights → assign (auto-route by class: mappings→data admin, CRM hygiene→owner) → fix path: in-source deep link / in-RIG mapping or merge → re-validation on next sync → auto-close + confidence restoration.
- **AI:** D.11 plain-language explanation.
- **Notifications:** weekly DQ digest; critical issues immediate.
- **Metrics:** MTTR by class; % insights degraded by data issues (trend down).

### WF-14. Feedback on a bad insight
- **Trigger:** user hits `incorrect` / `not useful` etc.
- **System:** verdict + optional context captured → linked to insight/model versions → precision dashboards update → threshold-tuning suggestions accumulate for admin review (never silent auto-tuning of published configs) → user sees "what happened with my feedback" trail (closes the loop, sustains participation).
- **AI:** clustering of feedback themes for the admin review queue (labeled).
- **Metrics:** feedback participation; precision trend post-tuning.

### WF-15. Learning from a confirmed churn or renewal
- **Trigger:** renewal outcome recorded (CRM closed-won/lost on renewal opp, subscription cancellation, or manual).
- **System:** outcome propagates to risk lifecycle (`outcome_known`) → postmortem record assembled (signals timeline, actions, forecast history) → root-cause tagging session (human selects from taxonomy; D.9 hypotheses assist) → labels join training/calibration sets (intervention-stratified, doc 9 C) → FN check (churn never flagged → FN report + detector gap analysis).
- **Approvals:** root-cause final tag = human only.
- **Metrics:** label coverage; calibration improvement; FN rate trend.

### WF-16. Admin configures a segment-specific health score
- **Trigger:** model admin edits weights for segment.
- **System:** draft config → backtest preview (distribution shift, flag diff, calibration) → four-eyes approval if exec-report-affecting → publish → `score_version` bump → timelines annotated → monitoring window with rollback affordance.
- **Audit:** config diff, approver, backtest snapshot.
- **Failure:** backtest degrades calibration beyond guardrail → publish blocked with override-with-justification path.
- **Metrics:** post-change acceptance/precision delta.

### WF-17. Connector failure and freshness degradation
- **Trigger:** sync errors exceed budget or freshness SLA breach.
- **System:** connector → `degraded/action_required` → affected accounts computed → dependent scores/signals flagged degraded confidence; evaluation suspended where policy demands (WF-6 rule) → data admin notified with runbook link → fix → replay from checkpoint/DLQ → freshness restored → flags cleared.
- **Notifications:** data admin immediately; business users see banners only (no alarm spam).
- **Metrics:** MTTR; % time within freshness SLA.

### WF-18. Natural-language investigation question
- **Trigger:** user asks copilot. 
- **System:** D.12 parse → permission-scoped semantic-layer query → structured results → authorized retrieval for context → synthesis with citations → verification → render (answer, evidence, methodology, confidence, gaps) → optional follow-ups: save view / create tasks (approval flow).
- **Approvals:** any resulting action follows standard gates; Q&A itself read-only.
- **Audit:** question, compiled query, result count, user.
- **Failure:** unparseable → clarification request; partially supported → explicit unsupported-parts list; retrieval empty → honest "no data" (never synthesized filler).
- **Metrics:** answer parity vs. hand-built queries (eval suite); user rating; escalation-to-analyst rate (should fall).

### WF-19. Human-approved write-back to Salesforce/HubSpot
- **Trigger:** any flow reaching an external write (task, field update, opportunity draft, plan summary).
- **System:** compose payload → **preview diff UI** (exact objects/fields, before→after) → user approve → idempotent execution (external id + idempotency key) → result verified read-after-write → linked in timeline.
- **Approvals:** per-execution, or standing rule explicitly created by admin for a narrow scope (e.g., "task creation may auto-sync") — standing rules listed and revocable in admin.
- **Audit:** `writeback.executed` with payload hash, approver, connector identity.
- **Failure:** rejection by CRM (validation/permissions) → surfaced verbatim + retry after fix; partial batch → per-record status, no silent partial success.
- **Metrics:** write-back error rate; approval-to-execution latency.

### WF-20. Customer offboarding and data deletion
- **Trigger:** contract termination or verified deletion request from tenant org admin.
- **System:** grace-period export offer (structured export of tenant-owned artifacts) → deletion job: revoke connector tokens → purge operational rows (hard delete), object storage (delete + lifecycle verification), search/vector namespaces, caches, backups handled via crypto-shredding of per-tenant keys + backup expiry schedule (documented ≤35 days) → subprocessor deletion requests where applicable → **deletion certificate** generated (scope, timestamps, methods) → audit trail retained in de-identified form as legally required.
- **Approvals:** dual confirmation (tenant org admin + RIG success manager) with cooling-off window (default 7 days) — destructive and irreversible.
- **Audit:** every stage; certificate archived.
- **Failure:** partial-purge detection job re-runs until clean; failures page on-call.
- **Metrics:** completion within contractual SLA (30 days); zero residual-data findings in audits.
