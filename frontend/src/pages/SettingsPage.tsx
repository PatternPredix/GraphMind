import { useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../api";
import { Project, ProjectStats } from "../types";

interface Ctx {
  project: Project | null;
  setProject: (p: Project) => void;
}

export default function SettingsPage() {
  const { projectId } = useParams();
  const { project, setProject } = useOutletContext<Ctx>();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [guideline, setGuideline] = useState("");
  const [threshold, setThreshold] = useState(20);
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!project) return;
    setName(project.name);
    setDescription(project.description);
    setGuideline(project.guideline);
    setThreshold(project.auto_annotate_threshold);
  }, [project]);

  useEffect(() => {
    api.get<ProjectStats>(`/api/projects/${projectId}/stats`).then(setStats).catch(() => {});
  }, [projectId]);

  async function save() {
    const updated = await api.patch<Project>(`/api/projects/${projectId}`, {
      name,
      description,
      guideline,
      auto_annotate_threshold: threshold,
    });
    setProject(updated);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function deleteProject() {
    if (!confirm("Delete this project with ALL its documents and annotations? This cannot be undone."))
      return;
    if (!confirm("Are you absolutely sure?")) return;
    await api.delete(`/api/projects/${projectId}`);
    navigate("/");
  }

  return (
    <div>
      <h1>Settings</h1>
      {stats && (
        <div className="panel row" style={{ gap: 24 }}>
          <span><strong>{stats.total_documents}</strong> documents</span>
          <span><strong>{stats.confirmed_documents}</strong> confirmed</span>
          <span><strong>{stats.total_spans}</strong> entities</span>
          <span><strong>{stats.total_relations}</strong> relations</span>
          <span className="muted">
            {stats.unreviewed_model_spans + stats.unreviewed_model_relations} model
            suggestions awaiting review
          </span>
        </div>
      )}
      <div className="panel" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label>
          Project name
          <input style={{ width: "100%", marginTop: 4 }} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Description
          <textarea
            rows={2}
            style={{ width: "100%", marginTop: 4 }}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label>
          Annotation guideline (shown to annotators)
          <textarea
            rows={6}
            style={{ width: "100%", marginTop: 4 }}
            value={guideline}
            onChange={(e) => setGuideline(e.target.value)}
          />
        </label>
        <label>
          Auto-annotate threshold — minimum human annotations per label type before
          the Auto-Annotate button unlocks
          <input
            type="number"
            min={1}
            style={{ width: 120, marginTop: 4, display: "block" }}
            value={threshold}
            onChange={(e) => setThreshold(parseInt(e.target.value || "1", 10))}
          />
        </label>
        <div className="row">
          <button className="primary" onClick={save}>
            Save settings
          </button>
          {saved && <span className="success-text">Saved ✓</span>}
        </div>
      </div>
      <div className="panel">
        <h2>Danger zone</h2>
        <button className="danger" onClick={deleteProject}>
          Delete project
        </button>
      </div>
    </div>
  );
}
