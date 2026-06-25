import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, getToken } from "../api";
import { DocumentPage, ImportResult } from "../types";

export default function DocumentsPage() {
  const { projectId } = useParams();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [filter, setFilter] = useState("all");
  const [data, setData] = useState<DocumentPage | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [importing, setImporting] = useState(false);
  const [importFormat, setImportFormat] = useState("auto");
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [newText, setNewText] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      search,
      filter,
    });
    api
      .get<DocumentPage>(`/api/projects/${projectId}/documents?${params}`)
      .then((d) => {
        setData(d);
        setSelected(new Set());
      })
      .catch((e) => setError(e.message));
  }, [projectId, page, pageSize, search, filter]);

  useEffect(load, [load]);

  async function uploadFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api.upload<ImportResult>(
        `/api/projects/${projectId}/import?format=${importFormat}`,
        form
      );
      setImportResult(result);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  }

  async function deleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`Delete ${selected.size} document(s) and all their annotations?`)) return;
    await api.post(`/api/projects/${projectId}/documents/bulk-delete`, {
      document_ids: [...selected],
    });
    load();
  }

  async function deleteOne(id: number) {
    if (!confirm("Delete this document and all its annotations?")) return;
    await api.delete(`/api/projects/${projectId}/documents/${id}`);
    load();
  }

  async function addDocument() {
    if (!newText.trim()) return;
    await api.post(`/api/projects/${projectId}/documents`, { text: newText });
    setNewText("");
    setShowAdd(false);
    load();
  }

  function exportUrl(format: string) {
    // Token via query is not supported; do an authenticated fetch + blob download.
    return async () => {
      const res = await fetch(`/api/projects/${projectId}/export?format=${format}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = format === "conll" ? "export.conll" : `export_${format}.jsonl`;
      a.click();
      URL.revokeObjectURL(a.href);
    };
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const allChecked = data ? data.items.length > 0 && data.items.every((d) => selected.has(d.id)) : false;

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Documents {data ? `(${data.total})` : ""}</h1>
        <div className="row">
          <select value={importFormat} onChange={(e) => setImportFormat(e.target.value)}>
            <option value="auto">Auto-detect (recommended)</option>
            <option value="jsonl">JSONL (entities + relations)</option>
            <option value="text_lines">Text — one doc per line</option>
            <option value="text">Text — whole file is one doc</option>
          </select>
          <input
            ref={fileInput}
            type="file"
            style={{ display: "none" }}
            onChange={uploadFile}
          />
          <button
            className="primary"
            disabled={importing}
            onClick={() => fileInput.current?.click()}
          >
            {importing ? "Importing…" : "⬆ Import"}
          </button>
          <button onClick={exportUrl("jsonl")}>⬇ Export JSONL</button>
          <button onClick={exportUrl("conll")}>⬇ CoNLL</button>
          <button onClick={() => setShowAdd(true)}>+ Add document</button>
        </div>
      </div>

      {error && <div className="panel error-text">{error}</div>}
      {importResult && (
        <div className="panel">
          <strong>Import complete:</strong> {importResult.imported_documents} documents,{" "}
          {importResult.imported_spans} entities, {importResult.imported_relations} relations.
          {importResult.created_entity_types.length > 0 && (
            <> New entity types: {importResult.created_entity_types.join(", ")}.</>
          )}
          {importResult.created_relation_types.length > 0 && (
            <> New relation types: {importResult.created_relation_types.join(", ")}.</>
          )}
          {importResult.warnings.length > 0 && (
            <div className="error-text" style={{ marginTop: 6 }}>
              {importResult.warnings.slice(0, 5).map((w, i) => (
                <div key={i}>{w}</div>
              ))}
            </div>
          )}
          <button className="small" style={{ marginTop: 8 }} onClick={() => setImportResult(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="row" style={{ marginBottom: 12 }}>
        <input
          placeholder="Search text…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setPage(1);
              setSearch(searchInput);
            }
          }}
          style={{ width: 280 }}
        />
        <select
          value={filter}
          onChange={(e) => {
            setPage(1);
            setFilter(e.target.value);
          }}
        >
          <option value="all">All documents</option>
          <option value="unconfirmed">Unconfirmed</option>
          <option value="confirmed">Confirmed</option>
          <option value="unreviewed">Needs review (model)</option>
        </select>
        {selected.size > 0 && (
          <button className="danger" onClick={deleteSelected}>
            🗑 Delete selected ({selected.size})
          </button>
        )}
      </div>

      <table className="data">
        <thead>
          <tr>
            <th style={{ width: 30 }}>
              <input
                type="checkbox"
                checked={allChecked}
                onChange={(e) => {
                  if (e.target.checked) setSelected(new Set(data?.items.map((d) => d.id)));
                  else setSelected(new Set());
                }}
              />
            </th>
            <th>Text</th>
            <th style={{ width: 90 }}>Entities</th>
            <th style={{ width: 90 }}>Relations</th>
            <th style={{ width: 120 }}>Status</th>
            <th style={{ width: 140 }}></th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map((d) => (
            <tr key={d.id}>
              <td>
                <input
                  type="checkbox"
                  checked={selected.has(d.id)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(d.id);
                    else next.delete(d.id);
                    setSelected(next);
                  }}
                />
              </td>
              <td>
                <Link to={`/projects/${projectId}/annotate/${d.id}?filter=${filter}`}>
                  {d.snippet || <span className="muted">(empty)</span>}
                </Link>
              </td>
              <td>{d.span_count}</td>
              <td>{d.relation_count}</td>
              <td>
                {d.has_unreviewed ? (
                  <span className="badge orange">needs review</span>
                ) : d.is_confirmed ? (
                  <span className="badge green">confirmed</span>
                ) : (
                  <span className="badge">pending</span>
                )}
              </td>
              <td>
                <div className="row" style={{ flexWrap: "nowrap" }}>
                  <Link to={`/projects/${projectId}/annotate/${d.id}?filter=${filter}`}>
                    <button className="small">Annotate</button>
                  </Link>
                  <button className="small danger" onClick={() => deleteOne(d.id)}>
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {data && data.items.length === 0 && (
            <tr>
              <td colSpan={6} className="muted" style={{ textAlign: "center", padding: 24 }}>
                No documents. Import a file to get started.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="row" style={{ justifyContent: "center", marginTop: 14 }}>
        <button className="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          ← Prev
        </button>
        <span className="muted">
          Page {page} / {totalPages}
        </span>
        <button className="small" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
          Next →
        </button>
      </div>

      {showAdd && (
        <div className="modal-backdrop" onClick={() => setShowAdd(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Add document</h2>
            <textarea
              rows={8}
              style={{ width: "100%" }}
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              placeholder="Paste document text…"
              autoFocus
            />
            <div className="row" style={{ justifyContent: "flex-end", marginTop: 10 }}>
              <button onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="primary" onClick={addDocument}>
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
