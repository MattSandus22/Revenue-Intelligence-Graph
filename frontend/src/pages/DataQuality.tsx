import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api";
import { Severity } from "../components/badges";

interface Issue {
  id: string; issue_class: string; severity: string; title: string; impact: string;
  state: string; detected_at: string; resolved_at: string | null;
}

export default function DataQuality() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["dq"],
    queryFn: () => api.get<{ issues: Issue[] }>("/v1/admin/data-quality"),
  });
  const run = useMutation({
    mutationFn: () => api.post<{ open: number; resolved: number }>("/v1/admin/data-quality/run"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dq"] }),
  });

  if (error instanceof ApiError && error.status === 403)
    return <div className="banner warn">Data-quality administration requires a data-admin role.</div>;
  if (isLoading) return <div className="empty">Loading data-quality issues…</div>;

  const issues = data?.issues ?? [];
  const open = issues.filter((issue) => issue.state === "open");

  return (
    <div>
      <h1>Data Quality</h1>
      <p className="subtitle">
        {open.length} open issue{open.length === 1 ? "" : "s"} — open issues degrade the
        confidence of dependent scores and suppress affected signals.
      </p>
      <div className="btn-row" style={{ marginBottom: 16 }}>
        <button onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? "Running checks…" : "Run checks now"}
        </button>
        {run.data && (
          <span className="chip">open: {run.data.open} · resolved this run: {run.data.resolved}</span>
        )}
      </div>
      {issues.length === 0 ? (
        <div className="card empty">No data-quality issues recorded. Run the checks to scan.</div>
      ) : (
        <table className="data">
          <thead><tr>
            <th>Severity</th><th>Class</th><th>Issue</th><th>Impact</th><th>State</th><th>Detected</th>
          </tr></thead>
          <tbody>
            {issues.map((issue) => (
              <tr key={issue.id} style={issue.state === "resolved" ? { opacity: 0.55 } : undefined}>
                <td><Severity level={issue.severity} /></td>
                <td><span className="chip">{issue.issue_class}</span></td>
                <td>{issue.title}</td>
                <td style={{ fontSize: 13, color: "var(--text-dim)" }}>{issue.impact}</td>
                <td>{issue.state}{issue.resolved_at && ` (${issue.resolved_at.slice(0, 10)})`}</td>
                <td className="mono">{issue.detected_at.slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
