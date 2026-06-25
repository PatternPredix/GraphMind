import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { Eligibility, TrainingJob } from "../types";

const RUNNING = ["queued", "training", "annotating"];

export default function AutoAnnotatePage() {
  const { projectId } = useParams();
  const [ner, setNer] = useState<Eligibility | null>(null);
  const [re, setRe] = useState<Eligibility | null>(null);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [error, setError] = useState("");
  const pollTimer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [nerData, reData, jobData] = await Promise.all([
        api.get<Eligibility>(`/api/projects/${projectId}/auto-annotate/eligibility?task=ner`),
        api.get<Eligibility>(`/api/projects/${projectId}/auto-annotate/eligibility?task=re`),
        api.get<TrainingJob[]>(`/api/projects/${projectId}/jobs`),
      ]);
      setNer(nerData);
      setRe(reData);
      setJobs(jobData);
      return jobData;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
      return [];
    }
  }, [projectId]);

  // Poll while any job is running.
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      const jobData = await load();
      if (cancelled) return;
      if (jobData.some((j) => RUNNING.includes(j.status))) {
        pollTimer.current = window.setTimeout(tick, 2500);
      }
    }
    tick();
    return () => {
      cancelled = true;
      if (pollTimer.current) window.clearTimeout(pollTimer.current);
    };
  }, [load]);

  async function start(task: "ner" | "re") {
    setError("");
    try {
      await api.post(`/api/projects/${projectId}/auto-annotate`, { task });
      load().then((jobData) => {
        if (jobData.some((j) => RUNNING.includes(j.status))) {
          pollTimer.current = window.setTimeout(async function tick() {
            const jd = await load();
            if (jd.some((j) => RUNNING.includes(j.status))) {
              pollTimer.current = window.setTimeout(tick, 2500);
            }
          }, 2500);
        }
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start");
    }
  }

  const running = jobs.some((j) => RUNNING.includes(j.status));

  return (
    <div>
      <h1>Auto-Annotate</h1>
      <p className="muted">
        Train a model on your human annotations, then automatically annotate all
        remaining documents. Model suggestions are marked for review — they never
        overwrite human annotations.
      </p>
      {error && <div className="panel error-text">{error}</div>}

      <div className="row" style={{ alignItems: "stretch" }}>
        <TaskPanel
          title="Named Entity Recognition"
          subtitle="spaCy NER model, trained on your entity annotations"
          info={ner}
          running={running}
          onStart={() => start("ner")}
        />
        <TaskPanel
          title="Relation Extraction"
          subtitle="BERT-family classifier (DistilBERT/SpanBERT), trained on your relations"
          info={re}
          running={running}
          onStart={() => start("re")}
        />
      </div>

      <div className="panel">
        <h2>Job history</h2>
        {jobs.length === 0 && <span className="muted">No jobs yet.</span>}
        {jobs.map((j) => (
          <div key={j.id} style={{ borderBottom: "1px solid var(--border)", padding: "10px 0" }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>
                #{j.id} {j.task.toUpperCase()}
              </strong>
              <span
                className={`badge ${
                  j.status === "completed" ? "green" : j.status === "failed" ? "orange" : "blue"
                }`}
              >
                {j.status}
              </span>
            </div>
            {RUNNING.includes(j.status) && (
              <div className="progressbar" style={{ margin: "8px 0" }}>
                <div style={{ width: `${Math.round(j.progress * 100)}%` }} />
              </div>
            )}
            <div className="muted" style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>
              {j.message}
            </div>
            {j.status === "completed" && (
              <div className="muted" style={{ marginTop: 4 }}>
                {"f1" in j.metrics && (
                  <>
                    F1 {String(j.metrics.f1)} · P {String(j.metrics.precision)} · R{" "}
                    {String(j.metrics.recall)} ·{" "}
                  </>
                )}
                {j.annotated_count} documents annotated
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function TaskPanel({
  title,
  subtitle,
  info,
  running,
  onStart,
}: {
  title: string;
  subtitle: string;
  info: Eligibility | null;
  running: boolean;
  onStart: () => void;
}) {
  return (
    <div className="panel" style={{ flex: 1, minWidth: 320 }}>
      <h2>{title}</h2>
      <p className="muted" style={{ marginTop: -6 }}>{subtitle}</p>
      {info?.types.map((t) => (
        <div key={t.id} style={{ marginBottom: 8 }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 3 }}>
            <span>{t.name}</span>
            <span className={t.eligible ? "success-text" : "muted"}>
              {t.count} / {t.threshold}
            </span>
          </div>
          <div className="progressbar">
            <div
              style={{
                width: `${Math.min(100, (t.count / t.threshold) * 100)}%`,
                background: t.eligible ? "var(--success)" : "var(--primary)",
              }}
            />
          </div>
        </div>
      ))}
      {info && info.types.length === 0 && (
        <p className="muted">Define label types first (Labels page).</p>
      )}
      {info && !info.eligible && info.reason && <p className="muted">{info.reason}</p>}
      <button
        className="primary"
        disabled={!info?.eligible || running}
        onClick={onStart}
        style={{ marginTop: 8 }}
      >
        {running ? "A job is running…" : "🤖 Train & Auto-Annotate"}
      </button>
    </div>
  );
}
