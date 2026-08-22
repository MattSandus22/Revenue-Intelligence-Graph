import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, daysUntil, fmtMoney, WorkbenchInsight } from "../api";
import { Severity } from "../components/badges";
import { RiskExplanation } from "./RiskExplanation";

const DISMISS_REASONS = ["incorrect", "already_known", "not_actionable", "duplicate", "data_error"];
const NEXT: Record<string, string[]> = {
  detected: ["triaged"],
  triaged: ["accepted", "dismissed"],
  accepted: ["in_progress", "dismissed"],
  in_progress: ["mitigated", "not_mitigated"],
};

export default function Workbench() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<WorkbenchInsight | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["workbench"],
    queryFn: () => api.get<{ insights: WorkbenchInsight[]; ranking: string }>("/v1/workbench"),
  });

  const transition = useMutation({
    mutationFn: ({ id, to, reason }: { id: string; to: string; reason?: string }) =>
      api.post(`/v1/insights/${id}/transition?to_state=${to}${reason ? `&reason=${reason}` : ""}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["workbench"] }); setSelected(null); },
  });
  const feedback = useMutation({
    mutationFn: ({ id, verdict }: { id: string; verdict: string }) =>
      api.post(`/v1/insights/${id}/feedback?verdict=${verdict}`),
  });

  if (isLoading) return <div className="empty">Loading workbench…</div>;
  if (error) return <div className="banner error">{String(error)}</div>;
  const insights = data!.insights;

  return (
    <div>
      <h1>Risk &amp; Opportunity Workbench</h1>
      <p className="subtitle" title={data!.ranking}>
        Ranked by urgency — hover for the formula. {insights.length} open items.
      </p>
      {insights.length === 0 ? (
        <div className="card empty">Nothing needs triage. Connected sources are healthy and no open risks meet the threshold.</div>
      ) : (
        <table className="data">
          <thead><tr>
            <th>Account</th><th>Insight</th><th>Severity</th><th>ARR at stake</th>
            <th>Renewal</th><th>Confidence</th><th>State</th>
          </tr></thead>
          <tbody>
            {insights.map((insight) => {
              const days = daysUntil(insight.renewal_date);
              return (
                <tr key={insight.id} className="clickable" onClick={() => setSelected(insight)}>
                  <td><Link to={`/accounts/${insight.account_id}`} onClick={(e) => e.stopPropagation()}>{insight.account_name}</Link></td>
                  <td>{insight.title}</td>
                  <td><Severity level={insight.severity} /></td>
                  <td className="money">{fmtMoney(insight.arr_at_stake_cents)}</td>
                  <td>{days == null ? "—" : `${days}d`}</td>
                  <td className="mono">{Number(insight.confidence).toFixed(2)}</td>
                  <td><span className="chip">{insight.state}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {selected && (
        <div className="drawer">
          <button className="close" onClick={() => setSelected(null)}>×</button>
          <h2 style={{ marginTop: 0 }}>{selected.account_name}</h2>
          <div><Severity level={selected.severity} />{" "}
            <span className="money">{fmtMoney(selected.arr_at_stake_cents)}</span> at stake</div>
          <p>{selected.title}</p>

          <h2>Lifecycle — currently “{selected.state}”</h2>
          <div className="btn-row">
            {(NEXT[selected.state] ?? []).map((to) =>
              to === "dismissed" ? (
                <DismissButton key={to} onDismiss={(reason) =>
                  transition.mutate({ id: selected.id, to, reason })} />
              ) : (
                <button key={to} className="secondary"
                  onClick={() => transition.mutate({ id: selected.id, to })}>
                  → {to.replace("_", " ")}
                </button>
              ))}
          </div>
          {transition.error && <div className="banner error">{String(transition.error)}</div>}

          <h2>Why — score explanation &amp; evidence</h2>
          <RiskExplanation accountId={selected.account_id} />

          <h2>Was this insight useful?</h2>
          <div className="btn-row">
            {["correct", "incorrect", "useful", "not_useful", "missing_context", "already_known"].map((verdict) => (
              <button key={verdict} className="secondary"
                onClick={() => feedback.mutate({ id: selected.id, verdict })}>
                {verdict.replace("_", " ")}
              </button>
            ))}
          </div>
          {feedback.isSuccess && <div className="banner info">Feedback recorded — thank you.</div>}
        </div>
      )}
    </div>
  );
}

function DismissButton({ onDismiss }: { onDismiss: (reason: string) => void }) {
  const [open, setOpen] = useState(false);
  if (!open) return <button className="danger" onClick={() => setOpen(true)}>→ dismiss…</button>;
  return (
    <span>
      {DISMISS_REASONS.map((reason) => (
        <button key={reason} className="secondary" style={{ margin: 2 }}
          onClick={() => onDismiss(reason)}>{reason.replace("_", " ")}</button>
      ))}
    </span>
  );
}
