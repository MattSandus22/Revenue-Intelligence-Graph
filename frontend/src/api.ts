// API client — every request carries the bearer token; the backend enforces
// tenant scoping and roles server-side (the UI only hides, never protects).

// Same-origin by default (production container serves the SPA from FastAPI);
// the Vite dev server proxies /v1 to the backend (vite.config.ts).
const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("rig_token");
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401) {
    localStorage.removeItem("rig_token");
    window.location.href = "/login";
    throw new ApiError(401, "session expired");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch { /* non-JSON error body */ }
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ---- Types (mirroring backend payloads) ----

export interface Account {
  id: string; name: string; segment: string | null; tier: string | null;
  arr_cents: number | null; renewal_date: string | null;
  lifecycle_stage: string; plan_status: string;
}

export interface Signal {
  id: string; signal_type: string; detector_class: string; severity: string;
  confidence: string; rationale: string; state: string; occurrence_count: number;
  first_detected_at: string;
}

export interface Citation {
  claim_text: string; claim_class: string; kind: string; source_system: string;
  source_record_id: string; statement: string; event_at: string; freshness_at: string;
}

export interface RiskComponent {
  component: string; weight: string; norm_value: string; contribution: string;
  rationale: string; evidence_ids: string[]; citations: Citation[];
}

export interface RiskResponse {
  score: { value: string; reliability: string; score_version: string; as_of: string; inputs_hash: string };
  direction: string;
  probability?: { p_nonrenewal: number; calibration: string; basis: string };
  components: RiskComponent[];
}

export interface WorkbenchInsight {
  id: string; account_id: string; account_name: string; kind: string; title: string;
  severity: string; confidence: string; arr_at_stake_cents: number | null;
  state: string; state_reason: string | null; renewal_date: string | null;
  urgency: string; created_at: string; updated_at: string;
}

export interface TimelineEvent {
  kind: string; at: string; title: string; detail: string; source: string; status: string;
}

export interface BriefClaim {
  text: string; claim_class: string; evidence_ids: string[];
  verification: { status: string; reasons: string[] };
}

export interface Brief {
  id: string; state: string; period_start: string; period_end: string;
  sections: { key: string; title: string; claims: BriefClaim[] }[];
  pending_review: { account: string; finding: string; note: string }[];
  excluded_claims: (BriefClaim & { section: string })[];
  created_by: string; approved_by: string | null;
}

export const fmtMoney = (cents: number | null | undefined) =>
  cents == null ? "—" : `$${(cents / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export const fmtDate = (value: string | null | undefined) =>
  value == null ? "—" : new Date(value).toISOString().slice(0, 10);

export const daysUntil = (value: string | null | undefined) => {
  if (value == null) return null;
  return Math.round((new Date(value).getTime() - Date.now()) / 86_400_000);
};
