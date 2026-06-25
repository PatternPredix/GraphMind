import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import {
  EntityType,
  KeywordRule,
  RelationRule,
  RelationType,
  TrainingJob,
} from "../types";

const RUNNING = ["queued", "training", "annotating"];

export default function RulesPage() {
  const { projectId } = useParams();
  const [entityTypes, setEntityTypes] = useState<EntityType[]>([]);
  const [relationTypes, setRelationTypes] = useState<RelationType[]>([]);
  const [keywordRules, setKeywordRules] = useState<KeywordRule[]>([]);
  const [relationRules, setRelationRules] = useState<RelationRule[]>([]);
  const [job, setJob] = useState<TrainingJob | null>(null);
  const [error, setError] = useState("");
  const pollTimer = useRef<number | null>(null);

  const entityName = (id: number) => entityTypes.find((t) => t.id === id)?.name ?? "?";
  const relationName = (id: number) => relationTypes.find((t) => t.id === id)?.name ?? "?";

  const loadRules = useCallback(() => {
    api.get<KeywordRule[]>(`/api/projects/${projectId}/rules/keyword`).then(setKeywordRules);
    api.get<RelationRule[]>(`/api/projects/${projectId}/rules/relation`).then(setRelationRules);
  }, [projectId]);

  useEffect(() => {
    api.get<EntityType[]>(`/api/projects/${projectId}/entity-types`).then(setEntityTypes);
    api.get<RelationType[]>(`/api/projects/${projectId}/relation-types`).then(setRelationTypes);
    loadRules();
    return () => {
      if (pollTimer.current) window.clearTimeout(pollTimer.current);
    };
  }, [projectId, loadRules]);

  function pollJob(jobId: number) {
    async function tick() {
      const j = await api.get<TrainingJob>(`/api/projects/${projectId}/jobs/${jobId}`);
      setJob(j);
      if (RUNNING.includes(j.status)) {
        pollTimer.current = window.setTimeout(tick, 1500);
      }
    }
    tick();
  }

  async function apply(kind: "keyword" | "relation") {
    setError("");
    try {
      const j = await api.post<TrainingJob>(
        `/api/projects/${projectId}/rules/${kind}/apply`
      );
      setJob(j);
      pollJob(j.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start");
    }
  }

  const jobRunning = job !== null && RUNNING.includes(job.status);

  return (
    <div>
      <h1>Rules</h1>
      <p className="muted">
        Rules pre-populate annotations across the whole corpus. Keyword rules tag
        every occurrence of a word as an entity. Relation rules link entity pairs
        whose connecting text matches an example you describe. Applied annotations
        appear under the “Needs review” filter (relations) or as accepted entities
        (keywords).
      </p>
      {error && <div className="panel error-text">{error}</div>}

      {job && (
        <div className="panel">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>
              {job.task === "ner_rules" ? "Keyword rules" : "Relation rules"} job #{job.id}
            </strong>
            <span
              className={`badge ${
                job.status === "completed" ? "green" : job.status === "failed" ? "orange" : "blue"
              }`}
            >
              {job.status}
            </span>
          </div>
          {jobRunning && (
            <div className="progressbar" style={{ margin: "8px 0" }}>
              <div style={{ width: `${Math.round(job.progress * 100)}%` }} />
            </div>
          )}
          <div className="muted" style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>
            {job.message}
          </div>
        </div>
      )}

      {/* ---- Keyword rules ---- */}
      <div className="panel">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>NER keyword rules</h2>
          <button
            className="primary"
            disabled={keywordRules.length === 0 || jobRunning}
            onClick={() => apply("keyword")}
          >
            ⚡ Apply to all documents
          </button>
        </div>
        <table className="data" style={{ margin: "12px 0" }}>
          <thead>
            <tr>
              <th>Keyword</th>
              <th style={{ width: 140 }}>Entity type</th>
              <th style={{ width: 120 }}>Match</th>
              <th style={{ width: 80 }}></th>
            </tr>
          </thead>
          <tbody>
            {keywordRules.map((r) => (
              <tr key={r.id}>
                <td>
                  <code>{r.keyword}</code>
                </td>
                <td>{entityName(r.entity_type_id)}</td>
                <td className="muted">
                  {r.whole_word ? "whole word" : "substring"}
                  {r.case_sensitive ? ", case-sensitive" : ""}
                </td>
                <td>
                  <button
                    className="small danger"
                    onClick={async () => {
                      await api.delete(`/api/projects/${projectId}/rules/keyword/${r.id}`);
                      loadRules();
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {keywordRules.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No keyword rules yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <KeywordRuleForm
          entityTypes={entityTypes}
          onCreate={async (body) => {
            setError("");
            try {
              await api.post(`/api/projects/${projectId}/rules/keyword`, body);
              loadRules();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Failed");
            }
          }}
        />
      </div>

      {/* ---- Relation rules ---- */}
      <div className="panel">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Relation rules (embedding similarity)</h2>
          <button
            className="primary"
            disabled={relationRules.length === 0 || jobRunning}
            onClick={() => apply("relation")}
          >
            ⚡ Apply to all documents
          </button>
        </div>
        <p className="muted" style={{ marginTop: 4 }}>
          For each ordered pair of entities of the chosen types, the text spanning
          them is embedded and compared to your example sentence. Pairs scoring at
          or above the threshold get the relation (for review). The example is
          embedded once, when you save the rule.
        </p>
        <table className="data" style={{ margin: "12px 0" }}>
          <thead>
            <tr>
              <th style={{ width: 200 }}>Pattern</th>
              <th>Example sentence</th>
              <th style={{ width: 90 }}>Threshold</th>
              <th style={{ width: 80 }}></th>
            </tr>
          </thead>
          <tbody>
            {relationRules.map((r) => (
              <tr key={r.id}>
                <td>
                  <span className="badge">{entityName(r.head_entity_type_id)}</span>
                  <span className="rel-type" style={{ margin: "0 4px" }}>
                    —{relationName(r.relation_type_id)}→
                  </span>
                  <span className="badge">{entityName(r.tail_entity_type_id)}</span>
                </td>
                <td className="muted">“{r.description}”</td>
                <td>{r.threshold.toFixed(2)}</td>
                <td>
                  <button
                    className="small danger"
                    onClick={async () => {
                      await api.delete(`/api/projects/${projectId}/rules/relation/${r.id}`);
                      loadRules();
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {relationRules.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No relation rules yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <RelationRuleForm
          entityTypes={entityTypes}
          relationTypes={relationTypes}
          onCreate={async (body) => {
            setError("");
            try {
              await api.post(`/api/projects/${projectId}/rules/relation`, body);
              loadRules();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Failed");
            }
          }}
        />
      </div>
    </div>
  );
}

function KeywordRuleForm({
  entityTypes,
  onCreate,
}: {
  entityTypes: EntityType[];
  onCreate: (body: {
    entity_type_id: number;
    keyword: string;
    case_sensitive: boolean;
    whole_word: boolean;
  }) => Promise<void>;
}) {
  const [keyword, setKeyword] = useState("");
  const [typeId, setTypeId] = useState<number | "">("");
  const [wholeWord, setWholeWord] = useState(true);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [hint, setHint] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!keyword.trim()) {
      setHint("Enter a keyword before adding the rule.");
      return;
    }
    if (typeId === "") {
      setHint("Pick an entity type from the dropdown before adding the rule.");
      return;
    }
    setHint("");
    await onCreate({
      entity_type_id: Number(typeId),
      keyword: keyword.trim(),
      case_sensitive: caseSensitive,
      whole_word: wholeWord,
    });
    setKeyword("");
  }

  if (entityTypes.length === 0)
    return <p className="muted">Define entity types first (Labels page).</p>;

  return (
    <>
      <form className="row" onSubmit={submit}>
        <input
          placeholder="Keyword (e.g. Aspirin)"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          style={{ width: 220 }}
        />
        <span className="muted">→</span>
        <select
          value={typeId}
          onChange={(e) => {
            setTypeId(e.target.value ? Number(e.target.value) : "");
            setHint("");
          }}
        >
          <option value="">Entity type…</option>
          {entityTypes.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <label className="row" style={{ gap: 4 }}>
          <input type="checkbox" checked={wholeWord} onChange={(e) => setWholeWord(e.target.checked)} />
          whole word
        </label>
        <label className="row" style={{ gap: 4 }}>
          <input
            type="checkbox"
            checked={caseSensitive}
            onChange={(e) => setCaseSensitive(e.target.checked)}
          />
          case-sensitive
        </label>
        <button className="primary">Add rule</button>
      </form>
      {hint && (
        <div className="error-text" style={{ marginTop: 6 }}>
          {hint}
        </div>
      )}
    </>
  );
}

function RelationRuleForm({
  entityTypes,
  relationTypes,
  onCreate,
}: {
  entityTypes: EntityType[];
  relationTypes: RelationType[];
  onCreate: (body: {
    relation_type_id: number;
    head_entity_type_id: number;
    tail_entity_type_id: number;
    description: string;
    threshold: number;
    max_distance: number;
  }) => Promise<void>;
}) {
  const [head, setHead] = useState<number | "">("");
  const [tail, setTail] = useState<number | "">("");
  const [relId, setRelId] = useState<number | "">("");
  const [description, setDescription] = useState("");
  const [threshold, setThreshold] = useState(0.55);
  const [hint, setHint] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (head === "" || tail === "" || relId === "") {
      setHint("Pick a head entity, a relation, and a tail entity.");
      return;
    }
    if (!description.trim()) {
      setHint("Enter an example sentence describing the relation.");
      return;
    }
    setHint("");
    await onCreate({
      relation_type_id: Number(relId),
      head_entity_type_id: Number(head),
      tail_entity_type_id: Number(tail),
      description: description.trim(),
      threshold,
      max_distance: 200,
    });
    setDescription("");
  }

  if (entityTypes.length === 0 || relationTypes.length === 0)
    return (
      <p className="muted">
        Define at least one entity type and one relation type first (Labels page).
      </p>
    );

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="row">
        <select value={head} onChange={(e) => setHead(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Head entity…</option>
          {entityTypes.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <select value={relId} onChange={(e) => setRelId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Relation…</option>
          {relationTypes.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <select value={tail} onChange={(e) => setTail(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Tail entity…</option>
          {entityTypes.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>
      <input
        placeholder="Example sentence describing the relation, e.g. 'is the sibling of'"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="row">
        <label className="row" style={{ gap: 6 }}>
          Similarity threshold: <strong>{threshold.toFixed(2)}</strong>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
          />
        </label>
        <span className="muted">higher = stricter matches</span>
        <button className="primary" style={{ marginLeft: "auto" }}>
          Add rule
        </button>
      </div>
      {hint && <div className="error-text">{hint}</div>}
    </form>
  );
}
