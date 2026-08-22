import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, Brief } from "../api";
import { ClaimBadge } from "../components/badges";
import { useAuth } from "../auth";

export default function BriefPage() {
  const { role } = useAuth();
  const queryClient = useQueryClient();
  const [briefId, setBriefId] = useState<string | null>(null);
  const canManage = ["leader", "org_admin", "data_admin", "model_admin"].includes(role ?? "");

  const generate = useMutation({
    mutationFn: () => api.post<{ brief_id: string }>("/v1/briefs/generate"),
    onSuccess: (data) => setBriefId(data.brief_id),
  });
  const brief = useQuery({
    queryKey: ["brief", briefId],
    queryFn: () => api.get<{ brief: Brief }>(`/v1/briefs/${briefId}`),
    enabled: briefId != null,
  });
  const approve = useMutation({
    mutationFn: () => api.post(`/v1/briefs/${briefId}/approve`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["brief", briefId] }),
  });

  return (
    <div>
      <h1>Weekly Executive Brief</h1>
      <p className="subtitle">
        Every claim below passed the verification layer — click nothing on faith; every
        statement is labeled and cited. Unverified claims never appear in the body.
      </p>
      {canManage && (
        <div className="btn-row" style={{ marginBottom: 16 }}>
          <button onClick={() => generate.mutate()} disabled={generate.isPending}>
            {generate.isPending ? "Generating…" : "Generate this week's brief"}
          </button>
          {briefId && brief.data?.brief.state === "draft" && (
            <button className="secondary" onClick={() => approve.mutate()}>Approve for distribution</button>
          )}
        </div>
      )}
      {approve.error && (
        <div className="banner error">
          Approval blocked by the verification gate: {String(approve.error)}
        </div>
      )}
      {generate.error && <div className="banner error">{String(generate.error)}</div>}

      {!briefId && <div className="card empty">Generate a brief to review it here.</div>}
      {brief.data && <BriefView brief={brief.data.brief} />}
    </div>
  );
}

function BriefView({ brief }: { brief: Brief }) {
  return (
    <div>
      <div className="card">
        <strong>Period:</strong> {brief.period_start} → {brief.period_end} ·{" "}
        <span className="chip">{brief.state}</span>
        {brief.approved_by && <> · approved by {brief.approved_by}</>}
      </div>
      {brief.sections.map((section) => (
        <div key={section.key} className="card">
          <h2 style={{ marginTop: 0 }}>{section.title}</h2>
          {section.claims.length === 0 && <div className="empty">No verified claims in this section.</div>}
          {section.claims.map((claim, index) => (
            <div key={index} style={{ margin: "8px 0" }}>
              <ClaimBadge claimClass={claim.claim_class} />
              {claim.text}
              <span className="chip" title={claim.evidence_ids.join(", ")}>
                {claim.evidence_ids.length} evidence
              </span>
            </div>
          ))}
        </div>
      ))}
      {brief.pending_review.length > 0 && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Pending human review (excluded from body)</h2>
          {brief.pending_review.map((item, index) => (
            <div key={index} style={{ margin: "6px 0" }}>
              <ClaimBadge claimClass="ai_interpretation" />
              <strong>{item.account}:</strong> {item.finding}
              <div style={{ fontSize: 12, color: "var(--text-dim)" }}>{item.note}</div>
            </div>
          ))}
        </div>
      )}
      {brief.excluded_claims.length > 0 && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Excluded claims (failed verification)</h2>
          {brief.excluded_claims.map((claim, index) => (
            <div key={index} style={{ margin: "6px 0" }}>
              <span className="sev high">BLOCKED</span> {claim.text}
              <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                {claim.verification.reasons.join("; ")}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
