import { MouseEvent as ReactMouseEvent, useMemo } from "react";
import { EntityType, Span } from "../types";

export interface SelectionInfo {
  start: number;
  end: number;
  clientX: number;
  clientY: number;
}

interface Props {
  text: string;
  spans: Span[];
  entityTypes: Map<number, EntityType>;
  highlightedSpanIds: Set<number>;
  relationSourceId: number | null;
  onSelectText: (sel: SelectionInfo) => void;
  onClickSpan: (spanId: number, clientX: number, clientY: number) => void;
}

interface Segment {
  start: number;
  end: number;
  covering: Span[]; // innermost (shortest) first
  endingHere: Span[]; // spans whose end == segment end
}

export default function TextAnnotator({
  text,
  spans,
  entityTypes,
  highlightedSpanIds,
  relationSourceId,
  onSelectText,
  onClickSpan,
}: Props) {
  const segments = useMemo(() => buildSegments(text, spans), [text, spans]);

  function handleMouseUp() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
    const range = sel.getRangeAt(0);
    const start = resolveOffset(range.startContainer, range.startOffset);
    const end = resolveOffset(range.endContainer, range.endOffset);
    if (start === null || end === null) return;
    let [s, e] = start <= end ? [start, end] : [end, start];
    // Trim whitespace from the selection edges.
    while (s < e && /\s/.test(text[s])) s++;
    while (e > s && /\s/.test(text[e - 1])) e--;
    if (s >= e) return;
    const rect = range.getBoundingClientRect();
    onSelectText({ start: s, end: e, clientX: rect.left, clientY: rect.bottom });
  }

  function spanTagClick(e: ReactMouseEvent, spanId: number) {
    e.stopPropagation();
    e.preventDefault();
    onClickSpan(spanId, e.clientX, e.clientY);
  }

  return (
    <div className="doc-text" onMouseUp={handleMouseUp}>
      {segments.map((seg) => {
        const inner = seg.covering[0];
        const type = inner ? entityTypes.get(inner.entity_type_id) : undefined;
        const highlighted = seg.covering.some((sp) => highlightedSpanIds.has(sp.id));
        const isSource = seg.covering.some((sp) => sp.id === relationSourceId);
        const classes = [
          "seg",
          inner ? "in-span" : "",
          inner && inner.source === "model" && !inner.reviewed ? "model-span" : "",
          highlighted || isSource ? "selected-span" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return (
          <span key={`${seg.start}`}>
            <span
              className={classes}
              data-start={seg.start}
              style={type ? { background: type.color + "66" } : undefined}
              onClick={
                inner ? (e) => spanTagClick(e, inner.id) : undefined
              }
            >
              {text.slice(seg.start, seg.end)}
            </span>
            {seg.endingHere.map((sp) => {
              const t = entityTypes.get(sp.entity_type_id);
              if (!t) return null;
              return (
                <span
                  key={sp.id}
                  className="span-tag"
                  style={{ border: `1px solid ${t.color}` }}
                  title={
                    sp.source === "model"
                      ? `model suggestion${sp.confidence ? ` (${(sp.confidence * 100).toFixed(0)}%)` : ""}${sp.reviewed ? ", accepted" : " — needs review"}`
                      : "human annotation"
                  }
                  onClick={(e) => spanTagClick(e, sp.id)}
                >
                  {t.name}
                  {sp.source === "model" && !sp.reviewed ? " ?" : ""}
                </span>
              );
            })}
          </span>
        );
      })}
    </div>
  );
}

function buildSegments(text: string, spans: Span[]): Segment[] {
  const boundaries = new Set<number>([0, text.length]);
  for (const sp of spans) {
    boundaries.add(Math.max(0, Math.min(sp.start_offset, text.length)));
    boundaries.add(Math.max(0, Math.min(sp.end_offset, text.length)));
  }
  const sorted = [...boundaries].sort((a, b) => a - b);
  const segments: Segment[] = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const start = sorted[i];
    const end = sorted[i + 1];
    if (start === end) continue;
    const covering = spans
      .filter((sp) => sp.start_offset <= start && sp.end_offset >= end)
      .sort(
        (a, b) =>
          a.end_offset - a.start_offset - (b.end_offset - b.start_offset)
      );
    const endingHere = spans
      .filter((sp) => sp.end_offset === end && sp.start_offset <= start)
      .sort((a, b) => a.start_offset - b.start_offset);
    segments.push({ start, end, covering, endingHere });
  }
  return segments;
}

/** Map a DOM selection endpoint back to a character offset in the document
 *  text using the data-start attribute on segment elements. */
function resolveOffset(node: Node, offsetInNode: number): number | null {
  let el: HTMLElement | null = null;
  if (node.nodeType === Node.TEXT_NODE) {
    el = node.parentElement;
  } else if (node.nodeType === Node.ELEMENT_NODE) {
    el = node as HTMLElement;
  }
  while (el && !el.dataset?.start) {
    if (el.classList?.contains("doc-text")) return null;
    el = el.parentElement;
  }
  if (!el || el.dataset.start === undefined) return null;
  const base = parseInt(el.dataset.start, 10);
  return node.nodeType === Node.TEXT_NODE ? base + offsetInNode : base;
}
