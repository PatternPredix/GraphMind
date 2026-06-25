"""Tests for keyword (gazetteer) NER rules and embedding-based relation rules.

Keyword rules and the pure helper functions are always tested. The
embedding-based relation-rule flow is tested live if sentence-transformers is
installed and the encoder model can be loaded (needs internet on first run);
otherwise it is reported as SKIP without failing the suite.
"""
import io
import json
import os
import tempfile
import time

tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "test.db")
os.environ["MODELS_DIR"] = os.path.join(tmp, "models")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.rules_engine import find_matches  # noqa: E402
from app.ml.relation_rules import _ordered_pairs, pair_snippet  # noqa: E402

client = TestClient(app)
failures = []


def check(name, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {name} {'' if condition else detail}")
    if not condition:
        failures.append(name)


def wait_job(pid, job_id, timeout=600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/projects/{pid}/jobs/{job_id}", headers=AUTH).json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(1)
    return job


# ---------- pure helper unit tests (no DB, no ML) ----------
m = find_matches("Apple makes apple pie with APPLE.", "apple", False, True)
check("find_matches case-insensitive whole-word", m == [(0, 5), (12, 17), (27, 32)], str(m))
m = find_matches("Category cat caterpillar cat.", "cat", False, True)
check("find_matches whole-word only", m == [(9, 12), (25, 28)], str(m))
m = find_matches("Apple apple", "Apple", True, True)
check("find_matches case-sensitive", m == [(0, 5)], str(m))
m = find_matches("co-operate co-op", "co-op", False, True)
check("find_matches punctuation keyword", m == [(11, 16)], str(m))


class FakeSpan:
    def __init__(self, sid, tid, start, end):
        self.id, self.entity_type_id, self.start_offset, self.end_offset = sid, tid, start, end


spans = [FakeSpan(1, 10, 0, 4), FakeSpan(2, 10, 20, 24), FakeSpan(3, 11, 40, 45)]
pairs = list(_ordered_pairs(spans, 10, 10, 200))  # symmetric PERSON-PERSON
check("ordered_pairs symmetric single direction", pairs == [(spans[0], spans[1])], str(pairs))
pairs = list(_ordered_pairs(spans, 10, 11, 200))  # asymmetric
check("ordered_pairs asymmetric", (spans[0], spans[2]) in pairs and (spans[1], spans[2]) in pairs, str(pairs))
pairs = list(_ordered_pairs(spans, 10, 10, 5))  # distance cutoff
check("ordered_pairs distance cutoff", pairs == [], str(pairs))
check("pair_snippet covers both", pair_snippet("John and his brother Mike", FakeSpan(1, 1, 0, 4), FakeSpan(2, 1, 21, 25)) == "John and his brother Mike")


# ---------- setup project ----------
client.post("/api/auth/register", json={"username": "ann", "email": "a@x.com", "password": "secret123"})
AUTH = {"Authorization": f"Bearer {client.post('/api/auth/login', data={'username': 'ann', 'password': 'secret123'}).json()['access_token']}"}
pid = client.post("/api/projects", headers=AUTH, json={"name": "Rules"}).json()["id"]
per = client.post(f"/api/projects/{pid}/entity-types", headers=AUTH, json={"name": "PERSON"}).json()["id"]
org = client.post(f"/api/projects/{pid}/entity-types", headers=AUTH, json={"name": "ORG"}).json()["id"]


# ---------- keyword rule flow ----------
docs = [
    json.dumps({"text": "Apple shipped a new product. Apple is huge."}),
    json.dumps({"text": "I ate an apple and visited Apple Store."}),
    json.dumps({"text": "No brand here, just a Pineapple."}),
]
client.post(f"/api/projects/{pid}/import?format=jsonl", headers=AUTH,
            files={"file": ("d.jsonl", io.BytesIO("\n".join(docs).encode()), "application/json")})

r = client.post(f"/api/projects/{pid}/rules/keyword", headers=AUTH,
                json={"entity_type_id": org, "keyword": "Apple", "case_sensitive": True, "whole_word": True})
check("create keyword rule", r.status_code == 200, r.text)

r = client.post(f"/api/projects/{pid}/rules/keyword/apply", headers=AUTH)
check("start keyword job", r.status_code == 200, r.text)
job = wait_job(pid, r.json()["id"])
check("keyword job completed", job["status"] == "completed", str(job))
# "Apple" (case-sensitive) appears: doc1 x2, doc2 x1 ("Apple Store"); "apple"/"Pineapple" excluded
check("keyword spans_created == 3", job["metrics"].get("spans_created") == 3, str(job["metrics"]))

# verify offsets & source on doc 2
page = client.get(f"/api/projects/{pid}/documents", headers=AUTH).json()
doc2 = next(d for d in page["items"] if d["snippet"].startswith("I ate"))
detail = client.get(f"/api/projects/{pid}/documents/{doc2['id']}", headers=AUTH).json()
rule_spans = [s for s in detail["spans"] if s["source"] == "rule"]
check("keyword span correct offset/source",
      len(rule_spans) == 1 and detail["text"][rule_spans[0]["start_offset"]:rule_spans[0]["end_offset"]] == "Apple",
      str(rule_spans))

# idempotency: re-apply, count must not grow
r2 = client.post(f"/api/projects/{pid}/rules/keyword/apply", headers=AUTH)
job2 = wait_job(pid, r2.json()["id"])
check("keyword job idempotent", job2["metrics"].get("spans_created") == 0, str(job2["metrics"]))

r = client.get(f"/api/projects/{pid}/rules/keyword", headers=AUTH)
check("list keyword rules", r.status_code == 200 and len(r.json()) == 1, r.text)


# ---------- relation rule flow (embedding; needs ML + model) ----------
sib = client.post(f"/api/projects/{pid}/relation-types", headers=AUTH, json={"name": "sibling_of"}).json()["id"]


def person_doc(text, a, b):
    return json.dumps({"text": text, "entities": [
        {"id": 1, "label": "PERSON", "start_offset": text.index(a), "end_offset": text.index(a) + len(a)},
        {"id": 2, "label": "PERSON", "start_offset": text.index(b), "end_offset": text.index(b) + len(b)},
    ]})


rel_docs = [
    person_doc("Mary is the sister of Tom.", "Mary", "Tom"),
    person_doc("John and his brother Peter went home.", "John", "Peter"),
    person_doc("Alice met Bob at the conference yesterday.", "Alice", "Bob"),  # not siblings
]
client.post(f"/api/projects/{pid}/import?format=jsonl", headers=AUTH,
            files={"file": ("r.jsonl", io.BytesIO("\n".join(rel_docs).encode()), "application/json")})

r = client.post(f"/api/projects/{pid}/rules/relation", headers=AUTH, json={
    "relation_type_id": sib,
    "head_entity_type_id": per,
    "tail_entity_type_id": per,
    "description": "two people who are siblings, brother or sister of each other",
    "threshold": 0.3,
    "max_distance": 200,
})
if r.status_code == 400 and "not installed" in r.text:
    print("[SKIP] relation rule flow — sentence-transformers not installed")
elif r.status_code != 200:
    check("create relation rule", False, r.text)
else:
    rule = r.json()
    check("create relation rule (embedding cached)", rule["has_embedding"] and rule["embedding_model"], str(rule))
    job = wait_job(pid, client.post(f"/api/projects/{pid}/rules/relation/apply", headers=AUTH).json()["id"])
    if job["status"] != "completed":
        check("relation rule job", False, str(job))
    else:
        check("relation rule job completed", True)
        # Gather relations across docs
        total_rel, sibling_texts = 0, []
        for d in client.get(f"/api/projects/{pid}/documents", headers=AUTH).json()["items"]:
            det = client.get(f"/api/projects/{pid}/documents/{d['id']}", headers=AUTH).json()
            for rel in det["relations"]:
                total_rel += 1
                check("relation rule source/unreviewed", rel["source"] == "rule" and rel["reviewed"] is False, str(rel))
                sibling_texts.append(det["text"])
        check("sibling relations created on sibling docs", total_rel >= 2, f"created {total_rel}")
        check("sibling docs matched (Mary/John not Alice)",
              any("Mary" in t for t in sibling_texts) and not any("Alice met Bob" in t for t in sibling_texts),
              str(sibling_texts))

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    raise SystemExit(1)
print("All rules tests passed.")
