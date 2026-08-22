import { useQuery } from "@tanstack/react-query";
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

const Fact = ({ label, value, mono }: { label: string; value: string; mono?: boolean }) => (
  <div>
    <div style={{ fontSize: 11, textTransform: "uppercase", color: "var(--text-dim)" }}>{label}</div>
    <div className={mono ? "money" : undefined} style={{ fontSize: 16, fontWeight: 600 }}>{value}</div>
  </div>
);
