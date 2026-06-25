import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { EntityType, RelationType } from "../types";

const COLORS = [
  "#f87171", "#fb923c", "#fbbf24", "#a3e635", "#34d399",
  "#22d3ee", "#60a5fa", "#a78bfa", "#f472b6", "#94a3b8",
];

export default function LabelsPage() {
  const { projectId } = useParams();
  const [entityTypes, setEntityTypes] = useState<EntityType[]>([]);
  const [relationTypes, setRelationTypes] = useState<RelationType[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<EntityType[]>(`/api/projects/${projectId}/entity-types`).then(setEntityTypes);
    api.get<RelationType[]>(`/api/projects/${projectId}/relation-types`).then(setRelationTypes);
  }, [projectId]);
  useEffect(load, [load]);

  return (
    <div>
      <h1>Labels</h1>
      {error && <div className="panel error-text">{error}</div>}
      <div className="panel">
        <h2>Entity types (NER)</h2>
        <TypeEditor
          items={entityTypes}
          withHotkey
          onCreate={async (name, color, hotkey) => {
            try {
              await api.post(`/api/projects/${projectId}/entity-types`, { name, color, hotkey });
              setError("");
              load();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Failed");
            }
          }}
          onUpdate={async (id, name, color, hotkey) => {
            await api.patch(`/api/projects/${projectId}/entity-types/${id}`, { name, color, hotkey });
            load();
          }}
          onDelete={async (id) => {
            if (!confirm("Delete this entity type? All its annotations will be removed.")) return;
            await api.delete(`/api/projects/${projectId}/entity-types/${id}`);
            load();
          }}
        />
      </div>
      <div className="panel">
        <h2>Relation types</h2>
        <TypeEditor
          items={relationTypes.map((r) => ({ ...r, hotkey: "" }))}
          withHotkey={false}
          onCreate={async (name, color) => {
            try {
              await api.post(`/api/projects/${projectId}/relation-types`, { name, color });
              setError("");
              load();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Failed");
            }
          }}
          onUpdate={async (id, name, color) => {
            await api.patch(`/api/projects/${projectId}/relation-types/${id}`, { name, color });
            load();
          }}
          onDelete={async (id) => {
            if (!confirm("Delete this relation type? All its annotations will be removed.")) return;
            await api.delete(`/api/projects/${projectId}/relation-types/${id}`);
            load();
          }}
        />
      </div>
    </div>
  );
}

interface TypeItem {
  id: number;
  name: string;
  color: string;
  hotkey: string;
}

function TypeEditor({
  items,
  withHotkey,
  onCreate,
  onUpdate,
  onDelete,
}: {
  items: TypeItem[];
  withHotkey: boolean;
  onCreate: (name: string, color: string, hotkey: string) => Promise<void>;
  onUpdate: (id: number, name: string, color: string, hotkey: string) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [color, setColor] = useState(COLORS[items.length % COLORS.length]);
  const [hotkey, setHotkey] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    await onCreate(name.trim(), color, hotkey.trim().toLowerCase());
    setName("");
    setHotkey("");
    setColor(COLORS[(items.length + 1) % COLORS.length]);
  }

  return (
    <>
      <table className="data" style={{ marginBottom: 14 }}>
        <thead>
          <tr>
            <th>Name</th>
            <th style={{ width: 120 }}>Color</th>
            {withHotkey && <th style={{ width: 100 }}>Hotkey</th>}
            <th style={{ width: 90 }}></th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id}>
              <td>
                <span
                  className="badge"
                  style={{ background: t.color, borderColor: t.color, color: "#1f2430" }}
                >
                  {t.name}
                </span>
              </td>
              <td>
                <input
                  type="color"
                  value={t.color}
                  onChange={(e) => onUpdate(t.id, t.name, e.target.value, t.hotkey)}
                  style={{ width: 44, height: 28, padding: 2 }}
                />
              </td>
              {withHotkey && (
                <td>
                  <input
                    value={t.hotkey}
                    maxLength={1}
                    style={{ width: 48, textAlign: "center" }}
                    onChange={(e) =>
                      onUpdate(t.id, t.name, t.color, e.target.value.toLowerCase())
                    }
                  />
                </td>
              )}
              <td>
                <button className="small danger" onClick={() => onDelete(t.id)}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={withHotkey ? 4 : 3} className="muted">
                None defined yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <form className="row" onSubmit={submit}>
        <input
          placeholder="New type name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          type="color"
          value={color}
          onChange={(e) => setColor(e.target.value)}
          style={{ width: 44, height: 34, padding: 2 }}
        />
        {withHotkey && (
          <input
            placeholder="Key"
            value={hotkey}
            maxLength={1}
            style={{ width: 56, textAlign: "center" }}
            onChange={(e) => setHotkey(e.target.value)}
          />
        )}
        <button className="primary">Add</button>
      </form>
    </>
  );
}
