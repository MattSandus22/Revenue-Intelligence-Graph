import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, fmtMoney, RiskComponent } from "../api";
import { EvidenceList } from "../components/badges";

interface CopilotResult {
  intent: string;
  answer: string;
  results?: { id: string; name: string; arr_cents: number | null; renewal_date: string | null;
    plan_status?: string; risk_score: string | null }[];
  explanation?: { score: { value: string }; components: RiskComponent[] };
  methodology?: { applied_filters?: unknown[]; unsupported?: string[]; source?: string };
  data_gaps?: string[];
  disclaimer: string;
}

const SUGGESTIONS = [
  "Why is Acme at risk?",
  "Show accounts worth more than $50k renewing in the next 120 days with declining usage",
  "Which accounts have no active account plan?",
];

export default function Copilot() {
  const [question, setQuestion] = useState("");
  const askMutation = useMutation({
    mutationFn: (q: string) => api.post<CopilotResult>("/v1/copilot/ask", { question: q }),
  });

  const submit = (q: string) => {
    setQuestion(q);
    askMutation.mutate(q);
  };

  const error = askMutation.error;
  const result = askMutation.data;

  return (
    <div>
      <h1>Investigation Copilot</h1>
      <p className="subtitle">
        Questions are parsed into safe structured queries over your permission-scoped data.
        The model never answers from memory and never writes anything.
      </p>
      <div className="card">
        <form onSubmit={(e) => { e.preventDefault(); if (question.trim()) askMutation.mutate(question); }}>
          <input value={question} placeholder="Ask about accounts, renewals, risks…"
            onChange={(e) => setQuestion(e.target.value)} />
          <div className="btn-row">
            <button type="submit" disabled={askMutation.isPending || !question.trim()}>
              {askMutation.isPending ? "Working…" : "Ask"}
            </button>
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" className="secondary" onClick={() => submit(s)}>{s}</button>
            ))}
          </div>
        </form>
      </div>

      {error instanceof ApiError && error.status === 503 && (
        <div className="banner warn">
          Generative features are disabled on this server (no LLM gateway configured).
          Everything else in RIG remains fully functional.
        </div>
      )}
      {error && !(error instanceof ApiError && error.status === 503) && (
        <div className="banner error">{String(error)}</div>
      )}

      {result && (
        <>
          <div className="card">
            <strong>{result.answer}</strong>
            <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 6 }}>{result.disclaimer}</div>
          </div>
          {result.data_gaps && result.data_gaps.length > 0 && (
            <div className="banner warn">{result.data_gaps.join(" · ")}</div>
          )}
          {result.methodology?.unsupported && result.methodology.unsupported.length > 0 && (
            <div className="banner warn">
              Parts of the question were not applied:
              <ul style={{ margin: "4px 0 0 18px" }}>
                {result.methodology.unsupported.map((u, i) => <li key={i}>{u}</li>)}
              </ul>
            </div>
          )}
          {result.results && result.results.length > 0 && (
            <table className="data">
              <thead><tr><th>Account</th><th>ARR</th><th>Renewal</th><th>Plan</th><th>Risk</th></tr></thead>
              <tbody>
                {result.results.map((row) => (
                  <tr key={row.id}>
                    <td><Link to={`/accounts/${row.id}`}>{row.name}</Link></td>
                    <td className="money">{fmtMoney(row.arr_cents)}</td>
                    <td className="mono">{row.renewal_date ?? "—"}</td>
                    <td>{row.plan_status ?? "—"}</td>
                    <td className="mono">{row.risk_score == null ? "no score" : Math.round(Number(row.risk_score))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {result.explanation && (
            <div style={{ marginTop: 12 }}>
              <h2>Evidence</h2>
              {result.explanation.components
                .filter((c) => Number(c.contribution) > 0)
                .map((c) => (
                  <div className="card" key={c.component}>
                    <strong>{c.component.replace(/_/g, " ")}</strong>{" "}
                    <span className="mono">+{Number(c.contribution).toFixed(1)} pts</span>
                    <div style={{ color: "var(--text-dim)", fontSize: 13 }}>{c.rationale}</div>
                    <EvidenceList citations={c.citations} />
                  </div>
                ))}
            </div>
          )}
          {result.methodology?.source && (
            <div className="card" style={{ fontSize: 12, color: "var(--text-dim)" }}>
              Methodology: {result.methodology.source}
              {result.methodology.applied_filters &&
                <> · filters applied: <span className="mono">{JSON.stringify(result.methodology.applied_filters)}</span></>}
            </div>
          )}
        </>
      )}
    </div>
  );
}
