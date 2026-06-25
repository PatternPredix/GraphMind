import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Member } from "../types";

export default function MembersPage() {
  const { projectId } = useParams();
  const { user } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("annotator");
  const [error, setError] = useState("");

  // Admin: create a new user account
  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [created, setCreated] = useState("");

  const load = useCallback(() => {
    api.get<Member[]>(`/api/projects/${projectId}/members`).then(setMembers).catch(() => {});
  }, [projectId]);
  useEffect(load, [load]);

  async function addMember(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post(`/api/projects/${projectId}/members`, { username, role });
      setUsername("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  async function createUser(e: FormEvent) {
    e.preventDefault();
    setError("");
    setCreated("");
    try {
      await api.post("/api/auth/users", {
        username: newUsername,
        email: newEmail,
        password: newPassword,
      });
      setCreated(`User "${newUsername}" created. Add them as a member below.`);
      setNewUsername("");
      setNewEmail("");
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <div>
      <h1>Members</h1>
      {error && <div className="panel error-text">{error}</div>}
      <div className="panel">
        <table className="data" style={{ marginBottom: 14 }}>
          <thead>
            <tr>
              <th>Username</th>
              <th style={{ width: 140 }}>Role</th>
              <th style={{ width: 90 }}></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td>{m.username}</td>
                <td>
                  <span className={`badge ${m.role === "admin" ? "blue" : ""}`}>{m.role}</span>
                </td>
                <td>
                  <button
                    className="small danger"
                    onClick={async () => {
                      await api.delete(`/api/projects/${projectId}/members/${m.id}`);
                      load();
                    }}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form className="row" onSubmit={addMember}>
          <input
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="annotator">Annotator</option>
            <option value="admin">Project admin</option>
          </select>
          <button className="primary">Add member</button>
        </form>
      </div>

      {user?.is_admin && (
        <div className="panel">
          <h2>Create user account (server admin)</h2>
          {created && <div className="success-text" style={{ marginBottom: 8 }}>{created}</div>}
          <form className="row" onSubmit={createUser}>
            <input
              placeholder="Username"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              required
            />
            <input
              placeholder="Email"
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              required
            />
            <input
              placeholder="Password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={6}
            />
            <button className="primary">Create user</button>
          </form>
        </div>
      )}
    </div>
  );
}
