import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

const ROLES = ["leader", "contributor", "exec_readonly", "data_admin", "model_admin",
  "org_admin", "analyst"];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [tenants, setTenants] = useState<{ id: string; name: string }[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [role, setRole] = useState("leader");
  const [user, setUser] = useState("demo-user");
  const [manualToken, setManualToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [devAvailable, setDevAvailable] = useState(true);
  const [ssoAvailable, setSsoAvailable] = useState(false);

  useEffect(() => {
    api.get<{ sso: boolean; dev: boolean }>("/v1/auth/methods")
      .then((methods) => setSsoAvailable(methods.sso))
      .catch(() => setSsoAvailable(false));
    api.get<{ tenants: { id: string; name: string }[] }>("/v1/dev/tenants")
      .then((data) => {
        setTenants(data.tenants);
        if (data.tenants[0]) setTenantId(data.tenants[0].id);
      })
      .catch(() => setDevAvailable(false));
  }, []);

  const ssoLogin = async () => {
    setError(null);
    try {
      const { authorization_url } = await api.get<{ authorization_url: string }>("/v1/auth/login");
      window.location.href = authorization_url;
    } catch (e) {
      setError(String(e));
    }
  };

  const devLogin = async () => {
    setError(null);
    try {
      const result = await api.post<{ token: string; role: string }>(
        `/v1/dev/token?tenant_id=${tenantId}&role=${role}&user=${encodeURIComponent(user)}`);
      login(result.token, result.role);
      navigate("/");
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div style={{ maxWidth: 420, margin: "80px auto" }}>
      <h1>Revenue Intelligence Graph</h1>
      <p className="subtitle">The evidence-backed operating system for retaining and expanding B2B revenue.</p>
      {ssoAvailable && (
        <div className="card">
          <div className="btn-row">
            <button onClick={ssoLogin} style={{ width: "100%" }}>Sign in with SSO</button>
          </div>
        </div>
      )}
      <div className="card">
        {devAvailable ? (
          <>
            <div className="banner info">Development sign-in (production uses SSO).</div>
            <label>Workspace</label>
            <select value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
              {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <label>Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r}>{r}</option>)}
            </select>
            <label>User id</label>
            <input value={user} onChange={(e) => setUser(e.target.value)} />
            <div className="btn-row"><button onClick={devLogin}>Sign in</button></div>
          </>
        ) : (
          <>
            <div className="banner warn">Dev sign-in is disabled on this server. Paste a token issued by your administrator.</div>
            <label>Access token</label>
            <input value={manualToken} onChange={(e) => setManualToken(e.target.value)} />
            <div className="btn-row">
              <button onClick={() => { login(manualToken, "unknown"); navigate("/"); }}>Sign in</button>
            </div>
          </>
        )}
        {error && <div className="banner error" style={{ marginTop: 12 }}>{error}</div>}
      </div>
    </div>
  );
}
