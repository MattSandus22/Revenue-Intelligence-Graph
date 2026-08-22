import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Account, api, daysUntil, fmtMoney } from "../api";

export default function Renewals() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.get<{ accounts: Account[] }>("/v1/accounts"),
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
