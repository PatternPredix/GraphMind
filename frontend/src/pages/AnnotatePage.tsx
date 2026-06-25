import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api } from "../api";
import TextAnnotator, { SelectionInfo } from "../components/TextAnnotator";
import {
  DocumentDetail,
  EntityType,
  Relation,
  RelationType,
  Span,
} from "../types";

type Popup =
  | { kind: "entity"; x: number; y: number; range: { start: number; end: number } }
  | { kind: "span"; x: number; y: number; spanId: number }
  | { kind: "relation-type"; x: number; y: number; fromId: number; toId: number };

export default function AnnotatePage() {
  const { projectId, documentId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = searchParams.get("filter") ?? "all";
  const navigate = useNavigate();

  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [entityTypes, setEntityTypes] = useState<EntityType[]>([]);
  const [relationTypes, setRelationTypes] = useState<RelationType[]>([]);
  const [popup, setPopup] = useState<Popup | null>(null);
  const [relationSource, setRelationSource] = useState<number | null>(null);
  // "Sticky label": when set, selecting text immediately tags it with this
  // entity type instead of opening the entity-type menu.
  const [activeTypeId, setActiveTypeId] = useState<number | null>(null);
  const [highlighted, setHighlighted] = useState<Set<number>>(new Set());
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [empty, setEmpty] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const entityTypeMap = useMemo(
    () => new Map(entityTypes.map((t) => [t.id, t])),
    [entityTypes]
  );
  const relationTypeMap = useMemo(
    () => new Map(relationTypes.map((t) => [t.id, t])),
    [relationTypes]
  );
  const spanMap = useMemo(
    () => new Map((doc?.spans ?? []).map((s) => [s.id, s])),
    [doc]
  );

  useEffect(() => {
    api.get<EntityType[]>(`/api/projects/${projectId}/entity-types`).then(setEntityTypes);
    api.get<RelationType[]>(`/api/projects/${projectId}/relation-types`).then(setRelationTypes);
  }, [projectId]);

  // Load the requested document, or jump to the first one under the filter.
  useEffect(() => {
    let cancelled = false;
    setError("");
    setPopup(null);
    setRelationSource(null);
    async function load() {
      try {
        if (documentId) {
          const d = await api.get<DocumentDetail>(
            `/api/projects/${projectId}/documents/${documentId}?filter=${filter}`
          );
          if (!cancelled) {
            setDoc(d);
            setEmpty(false);
          }
        } else {
          const d = await api.get<DocumentDetail | null>(
            `/api/projects/${projectId}/documents/first?filter=${filter}`
          );
          if (cancelled) return;
          if (d) navigate(`/projects/${projectId}/annotate/${d.id}?filter=${filter}`, { replace: true });
          else {
            setDoc(null);
            setEmpty(true);
          }
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [projectId, documentId, filter, navigate]);

  const goTo = useCallback(
    (id: number | null) => {
      if (id !== null)
        navigate(`/projects/${projectId}/annotate/${id}?filter=${filter}`);
    },
    [navigate, projectId, filter]
  );

  async function mutate<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setSaving(true);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
      return undefined;
    } finally {
      setSaving(false);
    }
  }

  const base = `/api/projects/${projectId}/documents/${doc?.id}`;

  async function addSpan(typeId: number, range: { start: number; end: number }) {
    if (!doc) return;
    const created = await mutate(() =>
      api.post<Span>(`${base}/spans`, {
        entity_type_id: typeId,
        start_offset: range.start,
        end_offset: range.end,
      })
    );
    if (created) setDoc({ ...doc, spans: [...doc.spans, created] });
    setPopup(null);
    window.getSelection()?.removeAllRanges();
  }

  async function deleteSpan(spanId: number) {
    if (!doc) return;
    const ok = await mutate(() => api.delete(`${base}/spans/${spanId}`));
    if (ok !== undefined)
      setDoc({
        ...doc,
        spans: doc.spans.filter((s) => s.id !== spanId),
        relations: doc.relations.filter(
          (r) => r.from_span_id !== spanId && r.to_span_id !== spanId
        ),
      });
    setPopup(null);
  }

  async function changeSpanType(spanId: number, typeId: number) {
    if (!doc) return;
    const updated = await mutate(() =>
      api.patch<Span>(`${base}/spans/${spanId}`, { entity_type_id: typeId })
    );
    if (updated)
      setDoc({ ...doc, spans: doc.spans.map((s) => (s.id === spanId ? updated : s)) });
    setPopup(null);
  }

  async function setSpanReviewed(spanId: number, reviewed: boolean) {
    if (!doc) return;
    if (!reviewed) return deleteSpan(spanId); // reject = delete
    const updated = await mutate(() =>
      api.patch<Span>(`${base}/spans/${spanId}`, { reviewed: true })
    );
    if (updated)
      setDoc({ ...doc, spans: doc.spans.map((s) => (s.id === spanId ? updated : s)) });
    setPopup(null);
  }

  async function addRelation(typeId: number, fromId: number, toId: number) {
    if (!doc) return;
    const created = await mutate(() =>
      api.post<Relation>(`${base}/relations`, {
        relation_type_id: typeId,
        from_span_id: fromId,
        to_span_id: toId,
      })
    );
    if (created) setDoc({ ...doc, relations: [...doc.relations, created] });
    setPopup(null);
    setRelationSource(null);
  }

  async function deleteRelation(relationId: number) {
    if (!doc) return;
    const ok = await mutate(() => api.delete(`${base}/relations/${relationId}`));
    if (ok !== undefined)
      setDoc({ ...doc, relations: doc.relations.filter((r) => r.id !== relationId) });
  }

  async function setRelationReviewed(relationId: number, reviewed: boolean) {
    if (!doc) return;
    if (!reviewed) return deleteRelation(relationId);
    const updated = await mutate(() =>
      api.patch<Relation>(`${base}/relations/${relationId}`, { reviewed: true })
    );
    if (updated)
      setDoc({
        ...doc,
        relations: doc.relations.map((r) => (r.id === relationId ? updated : r)),
      });
  }

  async function reviewAll(action: "accept_all" | "reject_all") {
    if (!doc) return;
    const ok = await mutate(() => api.post(`${base}/review?action=${action}`));
    if (ok !== undefined) {
      const d = await api.get<DocumentDetail>(
        `/api/projects/${projectId}/documents/${doc.id}?filter=${filter}`
      );
      setDoc(d);
    }
  }

  async function confirmAndNext() {
    if (!doc) return;
    const updated = await mutate(() =>
      api.post<DocumentDetail>(`${base}/confirm?filter=${filter}`, {
        is_confirmed: !doc.is_confirmed,
      })
    );
    if (updated) {
      if (!doc.is_confirmed && updated.next_id !== null) goTo(updated.next_id);
      else setDoc(updated);
    }
  }

  async function deleteDocument() {
    if (!doc) return;
    if (!confirm("Delete this document and all its annotations?")) return;
    const next = doc.next_id ?? doc.prev_id;
    await mutate(() => api.delete(`/api/projects/${projectId}/documents/${doc.id}`));
    if (next !== null) goTo(next);
    else navigate(`/projects/${projectId}/documents`);
  }

  // Keyboard shortcuts.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.key === "Escape") {
        setPopup(null);
        setRelationSource(null);
        setActiveTypeId(null);
        return;
      }
      if (!doc) return;
      if (e.key === "ArrowLeft" && doc.prev_id !== null) {
        goTo(doc.prev_id);
      } else if (e.key === "ArrowRight" && doc.next_id !== null) {
        goTo(doc.next_id);
      } else if (popup?.kind === "entity") {
        const byHotkey = entityTypes.find(
          (t) => t.hotkey && t.hotkey === e.key.toLowerCase()
        );
        const byNumber = /^[1-9]$/.test(e.key)
          ? entityTypes[parseInt(e.key, 10) - 1]
          : undefined;
        const chosen = byHotkey ?? byNumber;
        if (chosen) {
          e.preventDefault();
          addSpan(chosen.id, popup.range);
        }
      } else if (!popup) {
        // No menu open: a label key toggles sticky-label mode for that type.
        const byHotkey = entityTypes.find(
          (t) => t.hotkey && t.hotkey === e.key.toLowerCase()
        );
        const byNumber = /^[1-9]$/.test(e.key)
          ? entityTypes[parseInt(e.key, 10) - 1]
          : undefined;
        const chosen = byHotkey ?? byNumber;
        if (chosen) {
          e.preventDefault();
          setActiveTypeId((prev) => (prev === chosen.id ? null : chosen.id));
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  function popupPosition(clientX: number, clientY: number) {
    const rect = containerRef.current?.getBoundingClientRect();
    return {
      x: clientX - (rect?.left ?? 0),
      y: clientY - (rect?.top ?? 0) + 8,
    };
  }

  function handleSelectText(sel: SelectionInfo) {
    if (entityTypes.length === 0) {
      setError("Define entity types first (Labels page).");
      return;
    }
    // Sticky-label mode: tag the selection directly, skipping the menu.
    if (activeTypeId !== null && entityTypeMap.has(activeTypeId)) {
      addSpan(activeTypeId, { start: sel.start, end: sel.end });
      return;
    }
    const { x, y } = popupPosition(sel.clientX, sel.clientY);
    setPopup({ kind: "entity", x, y, range: { start: sel.start, end: sel.end } });
  }

  function handleClickSpan(spanId: number, clientX: number, clientY: number) {
    const { x, y } = popupPosition(clientX, clientY);
    if (relationSource !== null && relationSource !== spanId) {
      setPopup({ kind: "relation-type", x, y, fromId: relationSource, toId: spanId });
    } else {
      setPopup({ kind: "span", x, y, spanId });
    }
  }

  const unreviewedCount = doc
    ? doc.spans.filter((s) => !s.reviewed).length +
      doc.relations.filter((r) => !r.reviewed).length
    : 0;

  if (empty) {
    return (
      <div>
        <Toolbar
          doc={null}
          filter={filter}
          onFilter={(f) => setSearchParams({ filter: f })}
          saving={saving}
        />
        <div className="panel muted">
          No documents match this filter. Import documents or change the filter.
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{ position: "relative" }}
      // Dismiss on mousedown (the start of a new selection/click), NOT on click:
      // a text-selection drag fires a trailing `click` right after `mouseup`,
      // which would instantly close the entity menu we just opened on mouseup.
      onMouseDown={() => setPopup(null)}
    >
      <Toolbar
        doc={doc}
        filter={filter}
        onFilter={(f) => setSearchParams({ filter: f })}
        onPrev={() => doc && goTo(doc.prev_id)}
        onNext={() => doc && goTo(doc.next_id)}
        onConfirm={confirmAndNext}
        onDelete={deleteDocument}
        saving={saving}
      />
      {error && <div className="panel error-text">{error}</div>}

      <div className="legend">
        {entityTypes.map((t, i) => {
          const active = activeTypeId === t.id;
          return (
            <button
              key={t.id}
              type="button"
              className={`legend-item${active ? " active" : ""}`}
              onClick={() => setActiveTypeId(active ? null : t.id)}
              title={
                active
                  ? "Sticky label on — click to turn off"
                  : `Click to auto-tag every selection as ${t.name}`
              }
            >
              <span className="color-dot" style={{ background: t.color }} />
              {t.name}
              <kbd>{t.hotkey || i + 1}</kbd>
            </button>
          );
        })}
      </div>

      {relationSource !== null && (
        <div className="relation-banner">
          🔗 Relation mode: click the <strong>target</strong> entity, or press{" "}
          <kbd>Esc</kbd> to cancel.
          <button className="small" onClick={() => setRelationSource(null)}>
            Cancel
          </button>
        </div>
      )}

      {activeTypeId !== null && entityTypeMap.has(activeTypeId) && (
        <div
          className="relation-banner"
          style={{ background: "#f0fdf4", borderColor: "#bbf7d0", color: "#15803d" }}
        >
          🏷️ Sticky label: every selection is tagged{" "}
          <strong>{entityTypeMap.get(activeTypeId)!.name}</strong>.
          <button className="small" onClick={() => setActiveTypeId(null)}>
            Turn off
          </button>
        </div>
      )}

      {unreviewedCount > 0 && (
        <div className="relation-banner" style={{ background: "#fffbeb", borderColor: "#fde68a", color: "var(--warning)" }}>
          🤖 {unreviewedCount} model suggestion(s) need review.
          <button className="small" onClick={() => reviewAll("accept_all")}>
            ✓ Accept all
          </button>
          <button className="small danger" onClick={() => reviewAll("reject_all")}>
            ✗ Reject all
          </button>
        </div>
      )}

      <div className="annotate-layout">
        <div className="annotate-main">
          <div className="panel" style={{ padding: 0 }}>
            {doc ? (
              <TextAnnotator
                text={doc.text}
                spans={doc.spans}
                entityTypes={entityTypeMap}
                highlightedSpanIds={highlighted}
                relationSourceId={relationSource}
                onSelectText={handleSelectText}
                onClickSpan={handleClickSpan}
              />
            ) : (
              <div className="doc-text muted">Loading…</div>
            )}
          </div>
          <div className="kbd-help">
            Select text to add an entity · click a label chip (or press its key)
            to auto-tag every selection with it · click an entity tag to edit,
            delete or link · <kbd>←</kbd>/<kbd>→</kbd> previous/next document ·{" "}
            <kbd>Esc</kbd> cancel — every change is saved instantly.
          </div>
        </div>

        <div className="annotate-side">
          <div className="panel">
            <h2>Relations ({doc?.relations.length ?? 0})</h2>
            {doc?.relations.length === 0 && (
              <span className="muted">
                Click an entity tag, choose “Add relation”, then click the target
                entity.
              </span>
            )}
            {doc?.relations.map((r) => {
              const from = spanMap.get(r.from_span_id);
              const to = spanMap.get(r.to_span_id);
              const t = relationTypeMap.get(r.relation_type_id);
              if (!from || !to || !t) return null;
              return (
                <div
                  key={r.id}
                  className={`relation-item ${!r.reviewed ? "unreviewed" : ""}`}
                  onMouseEnter={() =>
                    setHighlighted(new Set([r.from_span_id, r.to_span_id]))
                  }
                  onMouseLeave={() => setHighlighted(new Set())}
                >
                  <span className="rel-arg">
                    {doc.text.slice(from.start_offset, from.end_offset)}
                  </span>
                  <span className="rel-type" style={{ color: t.color }}>
                    —{t.name}→
                  </span>
                  <span className="rel-arg">
                    {doc.text.slice(to.start_offset, to.end_offset)}
                  </span>
                  {!r.reviewed && (
                    <>
                      <button
                        className="small"
                        title={`model suggestion${r.confidence ? ` (${(r.confidence * 100).toFixed(0)}%)` : ""}`}
                        onClick={() => setRelationReviewed(r.id, true)}
                      >
                        ✓
                      </button>
                      <button className="small danger" onClick={() => setRelationReviewed(r.id, false)}>
                        ✗
                      </button>
                    </>
                  )}
                  {r.reviewed && (
                    <button
                      className="small danger"
                      style={{ marginLeft: "auto" }}
                      onClick={() => deleteRelation(r.id)}
                    >
                      ✗
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          <div className="panel">
            <h2>Entities ({doc?.spans.length ?? 0})</h2>
            {doc?.spans
              .slice()
              .sort((a, b) => a.start_offset - b.start_offset)
              .map((s) => {
                const t = entityTypeMap.get(s.entity_type_id);
                return (
                  <div
                    key={s.id}
                    className={`relation-item ${!s.reviewed ? "unreviewed" : ""}`}
                    onMouseEnter={() => setHighlighted(new Set([s.id]))}
                    onMouseLeave={() => setHighlighted(new Set())}
                  >
                    <span className="color-dot" style={{ background: t?.color }} />
                    <span className="rel-arg" style={{ maxWidth: 150 }}>
                      {doc.text.slice(s.start_offset, s.end_offset)}
                    </span>
                    <span className="muted">{t?.name}</span>
                    {!s.reviewed ? (
                      <>
                        <button className="small" onClick={() => setSpanReviewed(s.id, true)}>
                          ✓
                        </button>
                        <button className="small danger" onClick={() => setSpanReviewed(s.id, false)}>
                          ✗
                        </button>
                      </>
                    ) : (
                      <button
                        className="small danger"
                        style={{ marginLeft: "auto" }}
                        onClick={() => deleteSpan(s.id)}
                      >
                        ✗
                      </button>
                    )}
                  </div>
                );
              })}
          </div>
        </div>
      </div>

      {popup && (
        <div
          className="floating-menu"
          style={{ left: popup.x, top: popup.y }}
          // Keep the menu open when pressing inside it (the container closes
          // popups on mousedown).
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          {popup.kind === "entity" && (
            <>
              <div className="menu-title">Entity type</div>
              {entityTypes.map((t, i) => (
                <button key={t.id} onClick={() => addSpan(t.id, popup.range)}>
                  <span className="color-dot" style={{ background: t.color }} />
                  {t.name}
                  <span className="hotkey-hint">{t.hotkey || i + 1}</span>
                </button>
              ))}
            </>
          )}
          {popup.kind === "span" && (
            <SpanMenu
              span={spanMap.get(popup.spanId)}
              entityTypes={entityTypes}
              onChangeType={(typeId) => changeSpanType(popup.spanId, typeId)}
              onDelete={() => deleteSpan(popup.spanId)}
              onAccept={() => setSpanReviewed(popup.spanId, true)}
              onStartRelation={() => {
                setRelationSource(popup.spanId);
                setPopup(null);
              }}
            />
          )}
          {popup.kind === "relation-type" && (
            <>
              <div className="menu-title">Relation type</div>
              {relationTypes.length === 0 && (
                <div className="menu-title">Define relation types first (Labels page)</div>
              )}
              {relationTypes.map((t) => (
                <button key={t.id} onClick={() => addRelation(t.id, popup.fromId, popup.toId)}>
                  <span className="color-dot" style={{ background: t.color }} />
                  {t.name}
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SpanMenu({
  span,
  entityTypes,
  onChangeType,
  onDelete,
  onAccept,
  onStartRelation,
}: {
  span: Span | undefined;
  entityTypes: EntityType[];
  onChangeType: (typeId: number) => void;
  onDelete: () => void;
  onAccept: () => void;
  onStartRelation: () => void;
}) {
  if (!span) return null;
  return (
    <>
      {span.source === "model" && !span.reviewed && (
        <>
          <div className="menu-title">
            Model suggestion
            {span.confidence ? ` · ${(span.confidence * 100).toFixed(0)}%` : ""}
          </div>
          <button onClick={onAccept}>✓ Accept suggestion</button>
        </>
      )}
      <button onClick={onStartRelation}>🔗 Add relation from here</button>
      <div className="menu-title">Change type</div>
      {entityTypes
        .filter((t) => t.id !== span.entity_type_id)
        .map((t) => (
          <button key={t.id} onClick={() => onChangeType(t.id)}>
            <span className="color-dot" style={{ background: t.color }} />
            {t.name}
          </button>
        ))}
      <button onClick={onDelete} style={{ color: "var(--danger)" }}>
        🗑 Delete entity
      </button>
    </>
  );
}

function Toolbar({
  doc,
  filter,
  onFilter,
  onPrev,
  onNext,
  onConfirm,
  onDelete,
  saving,
}: {
  doc: DocumentDetail | null;
  filter: string;
  onFilter: (f: string) => void;
  onPrev?: () => void;
  onNext?: () => void;
  onConfirm?: () => void;
  onDelete?: () => void;
  saving: boolean;
}) {
  return (
    <div className="toolbar">
      <button disabled={!doc || doc.prev_id === null} onClick={onPrev}>
        ← Prev
      </button>
      <span className="pos">
        {doc ? `${doc.position} / ${doc.total}` : "– / –"}
      </span>
      <button disabled={!doc || doc.next_id === null} onClick={onNext}>
        Next →
      </button>
      <select value={filter} onChange={(e) => onFilter(e.target.value)}>
        <option value="all">All documents</option>
        <option value="unconfirmed">Unconfirmed</option>
        <option value="confirmed">Confirmed</option>
        <option value="unreviewed">Needs review (model)</option>
      </select>
      <div className="spacer" style={{ flex: 1 }} />
      <span className="muted">{saving ? "Saving…" : "All changes saved ✓"}</span>
      {doc && (
        <>
          <button
            className={doc.is_confirmed ? "" : "primary"}
            onClick={onConfirm}
          >
            {doc.is_confirmed ? "✓ Confirmed (undo)" : "Confirm & next"}
          </button>
          <button className="danger" onClick={onDelete}>
            🗑 Delete doc
          </button>
        </>
      )}
    </div>
  );
}
