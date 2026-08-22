import { Citation } from "../api";

export const Severity = ({ level }: { level: string }) => (
  <span className={`sev ${level}`}>{level.toUpperCase()}</span>
);

const CLAIM_LABELS: Record<string, string> = {
  observed_fact: "FACT",
  model_prediction: "PREDICTION",
  ai_interpretation: "AI-INTERPRETED",
  recommendation: "SUGGESTED",
};

export const ClaimBadge = ({ claimClass }: { claimClass: string }) => (
  <span className={`claim-badge ${claimClass}`}>{CLAIM_LABELS[claimClass] ?? claimClass}</span>
);

export function EvidenceList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return <div className="empty">No evidence items.</div>;
  return (
    <div>
      {citations.map((citation, index) => (
        <div className="evidence-item" key={index}>
          <ClaimBadge claimClass={citation.claim_class} />
          {citation.statement}
          <div className="meta">
            {citation.source_system} · {citation.kind} · {citation.source_record_id} · evidence as of{" "}
            {citation.event_at?.slice(0, 10)} · freshness {citation.freshness_at?.slice(0, 10)}
          </div>
        </div>
      ))}
    </div>
  );
}
