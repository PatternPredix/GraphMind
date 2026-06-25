"""JSONL annotation file parsing and serialization.

Supported import formats:
  - JSONL with entities and relations (one JSON object per line):
      {"text": "...",
       "entities": [{"id": 1, "label": "PER", "start_offset": 0, "end_offset": 4}],
       "relations": [{"id": 1, "from_id": 1, "to_id": 2, "type": "works_at"}]}
  - Legacy span JSONL (entities as offset triples):
      {"text": "...", "labels": [[0, 4, "PER"], ...]}
  - Plain JSONL with just {"text": "..."} (any extra keys preserved as meta)
  - Plain text (one document per line, or one document per file)

Supported export formats: JSONL (entities+relations), legacy span JSONL,
and CoNLL 2003 (NER only).
"""
import json
from typing import Any, Dict, Iterable, List, Tuple

RESERVED_KEYS = {"text", "entities", "relations", "labels", "label", "id"}


class ParsedDocument:
    def __init__(self, text: str, meta: Dict[str, Any]):
        self.text = text
        self.meta = meta
        # (source_id, label, start, end) — source_id is the id within the file
        self.entities: List[Tuple[Any, str, int, int]] = []
        # (from_source_id, to_source_id, type)
        self.relations: List[Tuple[Any, Any, str]] = []


def parse_jsonl(content: str) -> Tuple[List[ParsedDocument], List[str]]:
    """Parse JSONL annotation content. Returns (documents, warnings)."""
    docs: List[ParsedDocument] = []
    warnings: List[str] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"line {line_no}: invalid JSON, skipped")
            continue
        if not isinstance(record, dict) or "text" not in record:
            warnings.append(f"line {line_no}: no 'text' field, skipped")
            continue
        text = record["text"]
        if not isinstance(text, str):
            warnings.append(f"line {line_no}: 'text' is not a string, skipped")
            continue
        meta = {k: v for k, v in record.items() if k not in RESERVED_KEYS}
        doc = ParsedDocument(text, meta)

        entities = record.get("entities")
        if isinstance(entities, list):
            for ent in entities:
                if not isinstance(ent, dict):
                    continue
                try:
                    start = int(ent["start_offset"])
                    end = int(ent["end_offset"])
                    label = str(ent["label"])
                except (KeyError, TypeError, ValueError):
                    warnings.append(f"line {line_no}: malformed entity skipped")
                    continue
                if not _valid_span(start, end, len(text)):
                    warnings.append(
                        f"line {line_no}: entity [{start},{end}) out of bounds, skipped"
                    )
                    continue
                doc.entities.append((ent.get("id"), label, start, end))

        # Legacy format: "labels": [[start, end, "LABEL"], ...]
        labels = record.get("labels") or record.get("label")
        if isinstance(labels, list) and not entities:
            for item in labels:
                if (
                    isinstance(item, list)
                    and len(item) == 3
                    and isinstance(item[2], str)
                ):
                    try:
                        start, end = int(item[0]), int(item[1])
                    except (TypeError, ValueError):
                        continue
                    if not _valid_span(start, end, len(text)):
                        warnings.append(
                            f"line {line_no}: label [{start},{end}) out of bounds, skipped"
                        )
                        continue
                    doc.entities.append((None, item[2], start, end))

        relations = record.get("relations")
        if isinstance(relations, list):
            for rel in relations:
                if not isinstance(rel, dict):
                    continue
                try:
                    from_id = rel["from_id"]
                    to_id = rel["to_id"]
                    rtype = str(rel["type"])
                except (KeyError, TypeError):
                    warnings.append(f"line {line_no}: malformed relation skipped")
                    continue
                doc.relations.append((from_id, to_id, rtype))

        docs.append(doc)
    return docs, warnings


def parse_plain_text(content: str, one_doc_per_line: bool) -> List[ParsedDocument]:
    if one_doc_per_line:
        return [
            ParsedDocument(line, {}) for line in content.splitlines() if line.strip()
        ]
    return [ParsedDocument(content, {})] if content.strip() else []


def _valid_span(start: int, end: int, text_len: int) -> bool:
    return 0 <= start < end <= text_len


# ---------- Export ----------

def export_jsonl(documents: Iterable[dict]) -> str:
    """documents: dicts with text, meta, entities, relations (see documents router)."""
    lines = []
    for doc in documents:
        record: Dict[str, Any] = {"id": doc["id"], "text": doc["text"]}
        record.update(doc.get("meta") or {})
        record["entities"] = [
            {
                "id": e["id"],
                "label": e["label"],
                "start_offset": e["start"],
                "end_offset": e["end"],
            }
            for e in doc["entities"]
        ]
        record["relations"] = [
            {"id": r["id"], "from_id": r["from_id"], "to_id": r["to_id"], "type": r["type"]}
            for r in doc["relations"]
        ]
        lines.append(json.dumps(record, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def export_legacy_jsonl(documents: Iterable[dict]) -> str:
    lines = []
    for doc in documents:
        record: Dict[str, Any] = {"id": doc["id"], "text": doc["text"]}
        record.update(doc.get("meta") or {})
        record["labels"] = [[e["start"], e["end"], e["label"]] for e in doc["entities"]]
        lines.append(json.dumps(record, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def export_conll(documents: Iterable[dict]) -> str:
    """CoNLL 2003 export (whitespace tokenization, BIO tags). NER only."""
    out_lines: List[str] = []
    for doc in documents:
        text = doc["text"]
        entities = sorted(doc["entities"], key=lambda e: e["start"])
        boundaries = sorted({e["start"] for e in entities} | {e["end"] for e in entities})
        tokens = _tokenize_with_offsets(text, boundaries)
        for tok, start, end in tokens:
            tag = "O"
            for ent in entities:
                if start >= ent["start"] and end <= ent["end"]:
                    prefix = "B" if start == ent["start"] else "I"
                    tag = f"{prefix}-{ent['label']}"
                    break
            out_lines.append(f"{tok} {tag}")
        out_lines.append("")  # blank line between documents
    return "\n".join(out_lines) + ("\n" if out_lines else "")


def _tokenize_with_offsets(
    text: str, boundaries: List[int] = ()
) -> List[Tuple[str, int, int]]:
    """Whitespace tokens, additionally split at entity boundaries so a tag
    change inside a token (e.g. trailing punctuation) yields separate tokens."""
    tokens = []
    boundary_set = set(boundaries)
    i = 0
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        j = i
        while j < n and not text[j].isspace():
            j += 1
            if j in boundary_set and j < n and not text[j].isspace():
                break
        tokens.append((text[i:j], i, j))
        i = j
    return tokens
