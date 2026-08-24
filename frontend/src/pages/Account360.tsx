import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, daysUntil, fmtDate, fmtMoney, Signal, TimelineEvent } from "../api";
import { Severity } from "../components/badges";
import { RiskExplanation } from "./RiskExplanation";

interface AccountDetail {
  account: {
    id: string; name: string; segment: string | null; tier: string | null;
    industry: string | null; lifecycle_stage: string; arr_cents: number | null;
    renewal_date: string | null; notice_days: number | null; auto_renew: boolean;
    plan: string | null; plan_status: string; domains: string[];
  };
  active_signals: Signal[];
}

export default function Account360() {
  const { accountId } = useParams();
  const detail = useQuery({
    queryKey: ["account", accountId],
    queryFn: () => api.get<AccountDetail>(`/v1/accounts/${accountId}`),
  });
  const timeline = useQuery({
    queryKey: ["timeline", accountId],
    queryFn: () => api.get<{ events: TimelineEvent[] }>(`/v1/accounts/${accountId}/timeline`),
  });

  if (detail.isLoading) return <div className="empty">Loading account…</div>;
  if (detail.error) return <div className="banner error">{String(detail.error)}</div>;
  const { account, active_signals } = detail.data!;
  const days = daysUntil(account.renewal_date);

  return (
    <div>
      <h1>{account.name}</h1>
      <p className="subtitle">
        {account.industry ?? "—"} · {account.segment ?? "—"} · tier {account.tier ?? "—"} ·{" "}
        {account.lifecycle_stage} · {account.domains.join(", ")}
      </p>

      <div className="card" style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
        <Fact label="ARR" value={fmtMoney(account.arr_cents)} mono />
        <Fact label="Renewal" value={account.renewal_date
          ? `${fmtDate(account.renewal_date)} (${days}d)` : "—"} />
        <Fact label="Notice period" value={account.notice_days ? `${account.notice_days}d` : "—"} />
        <Fact label="Auto-renew" value={account.auto_renew ? "yes" : "no"} />
        <Fact label="Plan" value={account.plan ?? "—"} />
        <Fact label="Account plan" value={account.plan_status} />
      </div>

      <h2>Renewal risk</h2>
      <RiskExplanation accountId={account.id} />

      <OutcomeRecorder accountId={account.id} accountName={account.name} />

      <h2>Active signals ({active_signals.length})</h2>
      {active_signals.length === 0 ? (
        <div className="card empty">No active signals for this account.</div>
      ) : (
        <table className="data">
          <thead><tr><th>Signal</th><th>Class</th><th>Severity</th><th>Confidence</th><th>Seen</th><th>Rationale</th></tr></thead>
          <tbody>
            {active_signals.map((signal) => (
              <tr key={signal.id}>
                <td className="mono">{signal.signal_type}</td>
                <td><span className="chip">{signal.detector_class}</span></td>
                <td><Severity level={signal.severity} /></td>
                <td className="mono">{Number(signal.confidence).toFixed(2)}</td>
                <td>×{signal.occurrence_count}</td>
                <td>{signal.rationale}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Timeline</h2>
      {timeline.data ? (
        <table className="data">
          <thead><tr><th>When</th><th>Type</th><th>Event</th><th>Detail</th><th>Source</th></tr></thead>
          <tbody>
            {timeline.data.events.map((event, index) => (
              <tr key={index}>
                <td className="mono">{event.at.slice(0, 10)}</td>
                <td><span className="chip">{event.kind}</span></td>
                <td>{event.title}</td>
                <td>{event.detail}</td>
                <td>{event.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <div className="empty">Loading timeline…</div>}
    </div>
  );
}

const CHURN_REASONS = ["product_gap", "price", "champion_loss", "unresolved_support",
  "competitor", "budget", "m_and_a", "other"];

interface OutcomeResult {
  outcome: string; was_flagged: boolean; detection_lead_days: number | null;
  intervention: string; surprise_churn: boolean;
}

function OutcomeRecorder({ accountId, accountName }: { accountId: string; accountName: string }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [outcome, setOutcome] = useState("renewed");
  const [rootCause, setRootCause] = useState("");
  const [nextRenewal, setNextRenewal] = useState("");
  const [notes, setNotes] = useState("");
  const record = useMutation({
    mutationFn: () => api.post<OutcomeResult>(`/v1/accounts/${accountId}/outcome`, {
      outcome,
      ...(rootCause ? { root_cause_primary: rootCause } : {}),
      ...(nextRenewal ? { next_renewal_date: nextRenewal } : {}),
      ...(notes ? { notes } : {}),
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["account", accountId] }),
  });
  const needsRootCause = outcome !== "renewed";

  if (!expanded) {
    return (
      <div className="btn-row" style={{ margin: "16px 0" }}>
        <button className="secondary" onClick={() => setExpanded(true)}>
          Record renewal outcome…
        </button>
      </div>
    );
  }
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Record outcome for {accountName}</h2>
      <label>Outcome</label>
      <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
        <option value="renewed">renewed</option>
        <option value="churned">churned</option>
        <option value="downgraded">downgraded</option>
      </select>
      {needsRootCause && (
        <>
          <label>Primary root cause (required)</label>
          <select value={rootCause} onChange={(e) => setRootCause(e.target.value)}>
            <option value="">choose…</option>
            {CHURN_REASONS.map((reason) => <option key={reason}>{reason}</option>)}
          </select>
        </>
      )}
      {outcome === "renewed" && (
        <>
          <label>Next renewal date (optional)</label>
          <input type="date" value={nextRenewal} onChange={(e) => setNextRenewal(e.target.value)} />
        </>
      )}
      <label>Notes</label>
      <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="btn-row">
        <button disabled={record.isPending || (needsRootCause && !rootCause)}
          onClick={() => record.mutate()}>Record outcome</button>
        <button className="secondary" onClick={() => setExpanded(false)}>Cancel</button>
      </div>
      {record.data && (
        <div className={`banner ${record.data.surprise_churn ? "warn" : "info"}`}
          style={{ marginTop: 10 }}>
          Recorded. {record.data.was_flagged
            ? `Flagged ${record.data.detection_lead_days} days before the outcome`
            : "Never flagged before the outcome"}
          {" · "}intervention: {record.data.intervention}
          {record.data.surprise_churn && " · SURPRISE CHURN (counts toward the FN report)"}
        </div>
      )}
      {record.error && <div className="banner error" style={{ marginTop: 10 }}>{String(record.error)}</div>}
    </div>
  );
}

const Fact = ({ label, value, mono }: { label: string; value: string; mono?: boolean }) => (
  <div>
    <div style={{ fontSize: 11, textTransform: "uppercase", color: "var(--text-dim)" }}>{label}</div>
    <div className={mono ? "money" : undefined} style={{ fontSize: 16, fontWeight: 600 }}>{value}</div>
  </div>
);
