import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export default function AuthCallback() {
  const [params] = useSearchParams();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  // the authorization code is single-use: StrictMode's double effect run (or a
  // remount) must not exchange it twice and clobber a completed sign-in
  const exchanged = useRef(false);

  useEffect(() => {
    if (exchanged.current) return;
    exchanged.current = true;
    const code = params.get("code");
    const state = params.get("state");
    if (!code || !state) {
      setError("Missing code/state — restart sign-in.");
      return;
    }
    api.get<{ token: string; role: string }>(
      `/v1/auth/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`)
      .then((result) => {
        login(result.token, result.role);
        navigate("/", { replace: true });
      })
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div style={{ maxWidth: 420, margin: "80px auto" }}>
        <div className="banner error">{error}</div>
        <a href="/login">Back to sign-in</a>
      </div>
    );
  }
  return <div className="empty" style={{ marginTop: 120 }}>Completing sign-in…</div>;
}
