import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [defaultActive, setDefaultActive] = useState(false);

  // On a fresh install the seeded admin/admin login is still active; show a
  // hint until the admin password has been changed.
  useEffect(() => {
    api
      .get<{ default_admin_active: boolean }>("/api/auth/setup-status")
      .then((s) => setDefaultActive(s.default_admin_active))
      .catch(() => {});
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <form className="login-card" onSubmit={submit}>
        <h1 style={{ marginBottom: 2 }}>GraphMind</h1>
        <p className="muted" style={{ margin: "0 0 6px" }}>
          NER &amp; RE annotation for knowledge graphs
        </p>
        <p className="muted" style={{ margin: 0 }}>
          Sign in to your account
        </p>
        {defaultActive && (
          <div
            className="panel"
            style={{
              borderLeft: "4px solid #f59e0b",
              background: "rgba(245,158,11,0.08)",
              margin: "4px 0",
            }}
          >
            First run — sign in with <code>admin</code> / <code>admin</code>, then change the
            password from the Admin page.
          </div>
        )}
        <input
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          required
        />
        <input
          placeholder="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <div className="error-text">{error}</div>}
        <button className="primary" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
