import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { User } from "../types";

export default function AdminPage() {
  const { user, logout } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [passwords, setPasswords] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  // New-user form
  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    api.get<User[]>("/api/auth/users").then(setUsers).catch(() => {});
  }, []);
  useEffect(load, [load]);

  // Only server admins may use this page.
  if (user && !user.is_admin) return <Navigate to="/" replace />;

  // Surface failures at the top of the page AND scroll there, so they aren't
  // missed when the action is far down the user table.
  function fail(err: unknown, fallback: string) {
    setNotice("");
    setError(err instanceof Error ? err.message : fallback);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function setPassword(e: FormEvent, target: User) {
    e.preventDefault();
    setError("");
    setNotice("");
    const pw = passwords[target.id] ?? "";
    if (!pw) {
      setError("Enter a new password first.");
      return;
    }
    setBusyId(target.id);
    try {
      await api.patch(`/api/auth/users/${target.id}/password`, { new_password: pw });
      setPasswords((p) => ({ ...p, [target.id]: "" }));
      setNotice(
        target.id === user?.id
          ? "Your password was changed."
          : `Password changed for "${target.username}".`
      );
    } catch (err) {
      fail(err, "Failed");
    } finally {
      setBusyId(null);
    }
  }

  async function createUser(e: FormEvent) {
    e.preventDefault();
    setError("");
    setNotice("");
    setCreating(true);
    try {
      await api.post("/api/auth/users", {
        username: newUsername.trim(),
        email: newEmail.trim(),
        password: newPassword,
        is_admin: newIsAdmin,
      });
      setNotice(`User "${newUsername.trim()}" created.`);
      setNewUsername("");
      setNewEmail("");
      setNewPassword("");
      setNewIsAdmin(false);
      load();
    } catch (err) {
      fail(err, "Failed to create user");
    } finally {
      setCreating(false);
    }
  }

  async function removeUser(target: User) {
    if (
      !confirm(
        `Remove user "${target.username}"? They will lose access immediately. This cannot be undone.`
      )
    )
      return;
    setError("");
    setNotice("");
    setBusyId(target.id);
    try {
      await api.delete(`/api/auth/users/${target.id}`);
      setNotice(`User "${target.username}" removed.`);
      load();
    } catch (err) {
      fail(err, "Failed to remove user");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div className="topbar">
        <Link to="/" className="brand">
          GraphMind
        </Link>
        <div className="spacer" />
        <Link to="/admin" className="username" style={{ textDecoration: "none" }}>
          {user?.username}
          {user?.is_admin ? " (admin)" : ""}
        </Link>
        <button className="small" onClick={logout}>
          Sign out
        </button>
      </div>
      <div className="page" style={{ margin: "0 auto" }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
          <h1 style={{ margin: 0 }}>Admin — Users &amp; access</h1>
          <Link to="/" className="small">
            ← Back to projects
          </Link>
        </div>

        <div
          className="panel"
          style={{ borderLeft: "4px solid #f59e0b", background: "rgba(245,158,11,0.08)" }}
        >
          <strong>⚠️ Security:</strong> a new install ships with the default account{" "}
          <code>admin / admin</code>. Change the admin password below immediately, and do
          not expose this server to untrusted networks while the default is in use.
        </div>

        {error && <div className="panel error-text">{error}</div>}
        {notice && <div className="panel success-text">{notice}</div>}

        {/* ---- Existing users ---- */}
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Users ({users.length})</h2>
          <table className="data">
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th style={{ width: 80 }}>Role</th>
                <th style={{ width: 300 }}>Set new password</th>
                <th style={{ width: 90 }}></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    {u.username}
                    {u.id === user?.id ? " (you)" : ""}
                  </td>
                  <td className="muted">{u.email}</td>
                  <td>
                    <span className={`badge ${u.is_admin ? "blue" : ""}`}>
                      {u.is_admin ? "admin" : "user"}
                    </span>
                  </td>
                  <td>
                    <form
                      className="row"
                      style={{ gap: 6 }}
                      onSubmit={(e) => setPassword(e, u)}
                    >
                      <input
                        type="password"
                        placeholder="New password"
                        value={passwords[u.id] ?? ""}
                        onChange={(e) =>
                          setPasswords((p) => ({ ...p, [u.id]: e.target.value }))
                        }
                        required
                      />
                      <button className="primary small" disabled={busyId === u.id}>
                        {busyId === u.id ? "…" : "Set"}
                      </button>
                    </form>
                  </td>
                  <td>
                    {u.id === user?.id ? (
                      <span className="muted">—</span>
                    ) : (
                      <button
                        className="small danger"
                        disabled={busyId === u.id}
                        onClick={() => removeUser(u)}
                      >
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ---- Add a user ---- */}
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Add a user</h2>
          <form className="row" style={{ flexWrap: "wrap", gap: 8 }} onSubmit={createUser}>
            <input
              placeholder="Username"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              required
              minLength={2}
            />
            <input
              type="email"
              placeholder="Email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              required
            />
            <input
              type="password"
              placeholder="Password (min 6)"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={6}
            />
            <label className="row" style={{ gap: 4 }}>
              <input
                type="checkbox"
                checked={newIsAdmin}
                onChange={(e) => setNewIsAdmin(e.target.checked)}
              />
              admin
            </label>
            <button className="primary" disabled={creating}>
              {creating ? "Creating…" : "Add user"}
            </button>
          </form>
          <p className="muted" style={{ marginBottom: 0 }}>
            Admins can manage users and all projects. Regular users only see projects
            they own or are added to. A user who owns projects can’t be removed until
            those projects are reassigned or deleted.
          </p>
        </div>
      </div>
    </>
  );
}
