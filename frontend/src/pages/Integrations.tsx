import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../api";

interface Source {
  id: string; type: string; name: string; status: string;
  cursors: Record<string, string>;
  last_run: { status: string; mode: string; stats: Record<string, Record<string, number>>;
    error: string | null; started_at: string; finished_at: string | null } | null;
}

// Mirrors backend REQUIRED_FIELDS — the server re-validates; this only drives the form.
const CREDENTIAL_FIELDS: Record<string, { field: string; label: string }[]> = {
  hubspot: [{ field: "access_token", label: "Private app access token" }],
  stripe: [{ field: "api_key", label: "Restricted API key (read-only)" }],
  zendesk: [
    { field: "subdomain", label: "Subdomain (…​.zendesk.com)" },
    { field: "email", label: "Admin email" },
    { field: "api_token", label: "API token" },
  ],
  salesforce: [
    { field: "instance_url", label: "Instance URL (…​.my.salesforce.com)" },
    { field: "access_token", label: "OAuth access token" },
  ],
};

export default function Integrations() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["sources"],
    queryFn: () => api.get<{ sources: Source[] }>("/v1/admin/sources"),
  });
  const [syncOutput, setSyncOutput] = useState<Record<string, string>>({});

  const sync = useMutation({
    mutationFn: (id: string) => api.post<{ status: string; stats?: unknown; error?: string }>(
      `/v1/admin/sources/${id}/sync`),
    onSuccess: (result, id) => {
      setSyncOutput((prev) => ({ ...prev, [id]: JSON.stringify(result.stats ?? result) }));
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (err, id) => {
      setSyncOutput((prev) => ({ ...prev, [id]: String(err) }));
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => api.del(`/v1/admin/sources/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  if (error instanceof ApiError && error.status === 403)
    return <div className="banner warn">Integration administration requires a data-admin role.</div>;

  return (
    <div>
      <h1>Integrations</h1>
      <p className="subtitle">
        Connector health and setup. Credentials are encrypted at rest and never
        shown again after entry.
      </p>
      {isLoading && <div className="empty">Loading sources…</div>}
      {data && data.sources.length === 0 && (
        <div className="card empty">No sources connected yet — add one below to start the graph.</div>
      )}
      {data?.sources.map((source) => (
        <div className="card" key={source.id}>
          <strong>{source.name}</strong> <span className="chip">{source.type}</span>{" "}
          <span className={`sev ${source.status === "active" ? "low" : "high"}`}>
            {source.status.toUpperCase()}
          </span>
          <div style={{ fontSize: 13, color: "var(--text-dim)", margin: "6px 0" }}>
            {source.last_run ? (
              <>Last run: {source.last_run.status} ({source.last_run.mode}) at{" "}
                {source.last_run.started_at?.slice(0, 19)}
                {source.last_run.error && <span className="sev high"> — {source.last_run.error}</span>}
              </>
            ) : "Never synced."}
            {Object.keys(source.cursors ?? {}).length > 0 && (
              <> · cursors: {Object.entries(source.cursors).map(([k, v]) => (
                <span className="chip" key={k}>{k}: {String(v).slice(0, 19)}</span>))}</>
            )}
          </div>
          <div className="btn-row">
            <button disabled={source.status === "disconnected" || sync.isPending}
              onClick={() => sync.mutate(source.id)}>
              {sync.isPending ? "Syncing…" : "Sync now"}
            </button>
            {source.status !== "disconnected" && (
              <DisconnectButton onConfirm={() => disconnect.mutate(source.id)} />
            )}
          </div>
          {syncOutput[source.id] && (
            <div className="mono" style={{ marginTop: 8, wordBreak: "break-all" }}>
              {syncOutput[source.id]}
            </div>
          )}
        </div>
      ))}
      <AddSourceForm onCreated={() => queryClient.invalidateQueries({ queryKey: ["sources"] })} />
    </div>
  );
}

function DisconnectButton({ onConfirm }: { onConfirm: () => void }) {
  const [armed, setArmed] = useState(false);
  if (!armed) return <button className="secondary" onClick={() => setArmed(true)}>Disconnect…</button>;
  return (
    <span>
      <span style={{ fontSize: 12, marginRight: 6 }}>
        Stops syncing and deletes credentials (synced data retained).
      </span>
      <button className="danger" onClick={onConfirm}>Confirm disconnect</button>
      <button className="secondary" onClick={() => setArmed(false)}>Cancel</button>
    </span>
  );
}

function AddSourceForm({ onCreated }: { onCreated: () => void }) {
  const [type, setType] = useState("hubspot");
  const [name, setName] = useState("");
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const create = useMutation({
    mutationFn: () => api.post<{ source_id: string; reconnected: boolean }>(
      "/v1/admin/sources", { type, name, credentials }),
    onSuccess: () => { setName(""); setCredentials({}); onCreated(); },
  });

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Add a source</h2>
      <label>Type</label>
      <select value={type} onChange={(e) => { setType(e.target.value); setCredentials({}); }}>
        {Object.keys(CREDENTIAL_FIELDS).map((t) => <option key={t}>{t}</option>)}
      </select>
      <label>Name</label>
      <input value={name} placeholder={`${type}-production`}
        onChange={(e) => setName(e.target.value)} />
      {CREDENTIAL_FIELDS[type].map(({ field, label }) => (
        <div key={field}>
          <label>{label}</label>
          <input type="password" value={credentials[field] ?? ""} autoComplete="off"
            onChange={(e) => setCredentials((prev) => ({ ...prev, [field]: e.target.value }))} />
        </div>
      ))}
      <div className="btn-row">
        <button disabled={create.isPending || !name.trim()} onClick={() => create.mutate()}>
          {create.isPending ? "Connecting…" : "Connect"}
        </button>
      </div>
      {create.isSuccess && (
        <div className="banner info" style={{ marginTop: 10 }}>
          {create.data.reconnected ? "Source reconnected with fresh credentials." : "Source connected."}
        </div>
      )}
      {create.error && <div className="banner error" style={{ marginTop: 10 }}>{String(create.error)}</div>}
    </div>
  );
}
