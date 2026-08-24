import { useQuery } from "@tanstack/react-query";
import { api, ApiError, RiskResponse } from "../api";
import { EvidenceList } from "../components/badges";

export function RiskExplanation({ accountId }: { accountId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["risk", accountId],
    queryFn: () => api.get<RiskResponse>(`/v1/accounts/${accountId}/risk`),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });

  if (isLoading) return <div className="empty">Loading explanation…</div>;
  if (error instanceof ApiError && error.status === 404)
    return <div className="banner warn">No score computed yet for this account.</div>;
  if (error) return <div className="banner error">{String(error)}</div>;

  const { score, components, probability } = data!;
  const reliability = Number(score.reliability);
  return (
    <div>
      <div className="score-chip" title={`version ${score.score_version} · inputs ${score.inputs_hash.slice(0, 12)}…`}>
        <span className="value">{Math.round(Number(score.value))}</span>
        <span>/100 renewal risk · higher = riskier</span>
        {probability && (
          <span className="claim-badge model_prediction" title={probability.basis}>
            P(non-renewal) {Math.round(probability.p_nonrenewal * 100)}%
            {probability.calibration === "default_prior" ? " · default prior" : " · fitted"}
          </span>
        )}
      </div>
      {reliability < 0.8 && (
        <div className="banner warn" style={{ marginTop: 8 }}>
          Data reliability {Math.round(reliability * 100)}% — some sources are missing or stale;
          treat this score with caution.
        </div>
      )}
      {components.map((component) => (
        <div key={component.component} className="card" style={{ marginTop: 10 }}>
          <strong>{component.component.replace(/_/g, " ")}</strong>{" "}
          <span className="mono">
            +{Number(component.contribution).toFixed(1)} pts (weight {(Number(component.weight) * 100).toFixed(0)}%)
          </span>
          <div style={{ color: "var(--text-dim)", fontSize: 13, margin: "4px 0" }}>{component.rationale}</div>
          <EvidenceList citations={component.citations} />
        </div>
      ))}
    </div>
  );
}
