import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Project } from "../types";

export default function ProjectsPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Project[]>("/api/projects").then(setProjects).catch(() => {});
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const project = await api.post<Project>("/api/projects", {
        name,
        description,
      });
      navigate(`/projects/${project.id}/labels`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <>
      <div className="topbar">
        <Link to="/" className="brand">
          GraphMind
        </Link>
        <div className="spacer" />
        {user?.is_admin ? (
          <Link
            to="/admin"
            className="username"
            style={{ textDecoration: "none" }}
            title="Admin — manage users & passwords"
          >
            {user.username} (admin)
          </Link>
        ) : (
          <span className="username">{user?.username}</span>
        )}
        <button className="small" onClick={logout}>
          Sign out
        </button>
      </div>
      <div className="page" style={{ margin: "0 auto" }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
          <h1 style={{ margin: 0 }}>Projects</h1>
          <button className="primary" onClick={() => setShowCreate(true)}>
            + New project
          </button>
        </div>
        {projects.length === 0 && (
          <div className="panel muted">No projects yet. Create one to get started.</div>
        )}
        {projects.map((p) => (
          <Link
            key={p.id}
            to={`/projects/${p.id}`}
            style={{ textDecoration: "none", color: "inherit" }}
          >
            <div className="panel" style={{ cursor: "pointer" }}>
              <h2 style={{ marginBottom: 4 }}>{p.name}</h2>
              <span className="muted">{p.description || "No description"}</span>
            </div>
          </Link>
        ))}
      </div>
      {showCreate && (
        <div className="modal-backdrop" onClick={() => setShowCreate(false)}>
          <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={create}>
            <h2>New project</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input
                placeholder="Project name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
              />
              <textarea
                placeholder="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
              />
              {error && <div className="error-text">{error}</div>}
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <button type="button" onClick={() => setShowCreate(false)}>
                  Cancel
                </button>
                <button className="primary">Create</button>
              </div>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
