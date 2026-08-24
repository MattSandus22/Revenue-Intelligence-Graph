import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Account, api, daysUntil, fmtMoney } from "../api";

interface OutcomesReport {
  outcomes: Record<string, number>;
  surprise_churn: { count: number; of_churned: number; rate: number | null };
  calibration: { labels: number; required: number; status: string };
}

export default function Renewals() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.get<{ accounts: Account[] }>("/v1/accounts"),
  });
  const outcomes = useQuery({
    queryKey: ["outcomes"],
    queryFn: () => api.get<OutcomesReport>("/v1/metrics/outcomes"),
  });
  if (isLoading) return <div className="empty">Loading renewals…</div>;
  if (error) return <div className="banner error">{String(error)}</div>;

  const withRenewal = data!.accounts
    .filter((account) => account.renewal_date != null)
    .sort((a, b) => a.renewal_date!.localeCompare(b.renewal_date!));
  const next180 = withRenewal.filter((account) => {
    const days = daysUntil(account.renewal_date)!;
    return days >= 0 && days <= 180;
  });
  const arrDue = next180.reduce((sum, account) => sum + (account.arr_cents ?? 0), 0);
  const uncovered = next180.filter((account) => account.plan_status !== "active");

  return (
    <div>
      <h1>Renewal Command Center</h1>
      <p className="subtitle">
        {next180.length} renewals in the next 180 days ·{" "}
        <span className="money">{fmtMoney(arrDue)}</span> ARR due ·{" "}
        {uncovered.length} without an active account plan
      </p>
      {uncovered.length > 0 && (
        <div className="banner warn">
          {uncovered.length} renewal{uncovered.length > 1 ? "s" : ""} within 180 days have no
          active account plan — coverage gap.
        </div>
      )}
      {outcomes.data && (
        <div className="card" style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 13 }}>
          <span><strong>Outcomes recorded:</strong>{" "}
            {Object.entries(outcomes.data.outcomes).map(([k, v]) => `${k} ${v}`).join(" · ") || "none yet"}
          </span>
          {outcomes.data.surprise_churn.of_churned > 0 && (
            <span><strong>Surprise churn:</strong>{" "}
              {outcomes.data.surprise_churn.count}/{outcomes.data.surprise_churn.of_churned}
              {outcomes.data.surprise_churn.rate != null &&
                ` (${Math.round(outcomes.data.surprise_churn.rate * 100)}%)`}
            </span>
          )}
          <span className="chip" title="docs/09 cold-start honesty">
            {outcomes.data.calibration.status}
          </span>
        </div>
      )}
      <table className="data">
        <thead><tr>
          <th>Account</th><th>ARR</th><th>Renewal</th><th>Days</th>
          <th>Segment / tier</th><th>Plan status</th><th>Stage</th>
        </tr></thead>
        <tbody>
          {withRenewal.map((account) => {
            const days = daysUntil(account.renewal_date)!;
            return (
              <tr key={account.id}>
                <td><Link to={`/accounts/${account.id}`}>{account.name}</Link></td>
                <td className="money">{fmtMoney(account.arr_cents)}</td>
                <td className="mono">{account.renewal_date}</td>
                <td style={days <= 90 ? { fontWeight: 700 } : undefined}>{days}d</td>
                <td>{account.segment ?? "—"} / {account.tier ?? "—"}</td>
                <td>
                  <span className="chip">{account.plan_status}</span>
                  {account.plan_status !== "active" && days <= 120 && (
                    <span className="sev high" style={{ marginLeft: 4 }}>NO PLAN</span>
                  )}
                </td>
                <td>{account.lifecycle_stage}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
