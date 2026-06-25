import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Project } from "../types";

export default function ProjectLayout() {
  const { projectId } = useParams();
  const { user, logout } = useAuth();
  const [project, setProject] = useState<Project | null>(null);

  useEffect(() => {
    api.get<Project>(`/api/projects/${projectId}`).then(setProject).catch(() => {});
  }, [projectId]);

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
      <div className="project-layout">
        <nav className="sidebar">
          <div className="project-name">{project?.name ?? "…"}</div>
          <NavLink to="annotate">✏️ Annotate</NavLink>
          <NavLink to="documents">📄 Documents</NavLink>
          <NavLink to="labels">🏷️ Labels</NavLink>
          <NavLink to="rules">📐 Rules</NavLink>
          <NavLink to="auto">🤖 Auto-Annotate</NavLink>
          <NavLink to="members">👥 Members</NavLink>
          <NavLink to="settings">⚙️ Settings</NavLink>
        </nav>
        <main className="page">
          <Outlet context={{ project, setProject }} />
        </main>
      </div>
    </>
  );
}
