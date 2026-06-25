"""End-to-end API smoke test against a temporary SQLite database."""
import io
import json
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name} {detail if not condition else ''}")
    if not condition:
        failures.append(name)


# --- auth ---
r = client.post("/api/auth/register", json={
    "username": "alice", "email": "alice@example.com", "password": "secret123"})
check("register first user (admin)", r.status_code == 200 and r.json()["is_admin"], r.text)

r = client.post("/api/auth/register", json={
    "username": "bob", "email": "bob@example.com", "password": "secret123"})
check("open registration closed", r.status_code == 403, r.text)

r = client.post("/api/auth/login", data={"username": "alice", "password": "secret123"})
check("login", r.status_code == 200, r.text)
token = r.json()["access_token"]
auth = {"Authorization": f"Bearer {token}"}

r = client.post("/api/auth/users", headers=auth, json={
    "username": "bob", "email": "bob@example.com", "password": "secret123"})
check("admin creates user", r.status_code == 200, r.text)

# --- project & labels ---
r = client.post("/api/projects", headers=auth, json={
    "name": "Test", "auto_annotate_threshold": 3})
check("create project", r.status_code == 200, r.text)
pid = r.json()["id"]

r = client.post(f"/api/projects/{pid}/entity-types", headers=auth,
                json={"name": "PER", "color": "#f00", "hotkey": "p"})
check("create entity type", r.status_code == 200, r.text)
per_id = r.json()["id"]
r = client.post(f"/api/projects/{pid}/entity-types", headers=auth, json={"name": "ORG"})
org_id = r.json()["id"]
r = client.post(f"/api/projects/{pid}/relation-types", headers=auth, json={"name": "works_at"})
check("create relation type", r.status_code == 200, r.text)
works_id = r.json()["id"]

# --- import JSONL (entities + relations) ---
jsonl = "\n".join([
    json.dumps({"text": "Steve Jobs founded Apple.",
                "entities": [
                    {"id": 1, "label": "PER", "start_offset": 0, "end_offset": 10},
                    {"id": 2, "label": "ORG", "start_offset": 19, "end_offset": 24}],
                "relations": [{"id": 1, "from_id": 1, "to_id": 2, "type": "works_at"}],
                "source": "wiki"}),
    json.dumps({"text": "Sundar Pichai leads Google.", "labels": [[0, 13, "PER"]]}),
    json.dumps({"text": "An unannotated document about Microsoft."}),
])
r = client.post(f"/api/projects/{pid}/import?format=jsonl", headers=auth,
                files={"file": ("data.jsonl", io.BytesIO(jsonl.encode()), "application/json")})
ok = r.status_code == 200
data = r.json() if ok else {}
check("import jsonl", ok and data["imported_documents"] == 3
      and data["imported_spans"] == 3 and data["imported_relations"] == 1, r.text)

# --- documents ---
r = client.get(f"/api/projects/{pid}/documents", headers=auth)
check("list documents", r.status_code == 200 and r.json()["total"] == 3, r.text)
docs = r.json()["items"]
doc1 = docs[0]["id"]

r = client.get(f"/api/projects/{pid}/documents/{doc1}", headers=auth)
detail = r.json()
check("doc detail with spans+relations",
      len(detail["spans"]) == 2 and len(detail["relations"]) == 1
      and detail["next_id"] is not None and detail["position"] == 1 and detail["total"] == 3,
      r.text)
check("span offsets preserved",
      sorted((s["start_offset"], s["end_offset"]) for s in detail["spans"]) == [(0, 10), (19, 24)],
      str(detail["spans"]))

# --- annotate doc 3 manually ---
doc3 = docs[2]["id"]
r = client.post(f"/api/projects/{pid}/documents/{doc3}/spans", headers=auth,
                json={"entity_type_id": org_id, "start_offset": 30, "end_offset": 39})
check("create span", r.status_code == 200, r.text)
span_a = r.json()["id"]
r = client.post(f"/api/projects/{pid}/documents/{doc3}/spans", headers=auth,
                json={"entity_type_id": per_id, "start_offset": 0, "end_offset": 2})
span_b = r.json()["id"]
r = client.post(f"/api/projects/{pid}/documents/{doc3}/relations", headers=auth,
                json={"relation_type_id": works_id, "from_span_id": span_b, "to_span_id": span_a})
check("create relation", r.status_code == 200, r.text)
rel_id = r.json()["id"]

r = client.post(f"/api/projects/{pid}/documents/{doc3}/spans", headers=auth,
                json={"entity_type_id": org_id, "start_offset": 30, "end_offset": 999})
check("reject out-of-bounds span", r.status_code == 400, r.text)

r = client.delete(f"/api/projects/{pid}/documents/{doc3}/relations/{rel_id}", headers=auth)
check("delete relation", r.status_code == 200, r.text)
r = client.delete(f"/api/projects/{pid}/documents/{doc3}/spans/{span_b}", headers=auth)
check("delete span", r.status_code == 200, r.text)

r = client.post(f"/api/projects/{pid}/documents/{doc1}/confirm", headers=auth,
                json={"is_confirmed": True})
check("confirm document", r.status_code == 200 and r.json()["is_confirmed"], r.text)

# --- filtered navigation ---
r = client.get(f"/api/projects/{pid}/documents/first?filter=unconfirmed", headers=auth)
check("first unconfirmed doc", r.status_code == 200 and r.json()["id"] != doc1, r.text)

# --- stats / eligibility ---
r = client.get(f"/api/projects/{pid}/stats", headers=auth)
check("stats", r.status_code == 200 and r.json()["total_documents"] == 3, r.text)

r = client.get(f"/api/projects/{pid}/auto-annotate/eligibility?task=ner", headers=auth)
elig = r.json()
check("ner eligibility computed", r.status_code == 200 and elig["threshold"] == 3
      and any(t["name"] == "PER" and t["count"] == 2 for t in elig["types"]), r.text)
check("ner not yet eligible", elig["eligible"] is False, str(elig))

r = client.post(f"/api/projects/{pid}/auto-annotate", headers=auth, json={"task": "ner"})
check("auto-annotate blocked below threshold", r.status_code == 400, r.text)

# --- export ---
r = client.get(f"/api/projects/{pid}/export?format=jsonl", headers=auth)
lines = [json.loads(line) for line in r.text.strip().splitlines()]
check("export jsonl roundtrip", r.status_code == 200 and len(lines) == 3
      and lines[0]["entities"][0]["start_offset"] == 0
      and lines[0]["relations"][0]["type"] == "works_at"
      and lines[0]["source"] == "wiki", r.text[:300])

r = client.get(f"/api/projects/{pid}/export?format=conll", headers=auth)
check("export conll", r.status_code == 200 and "Steve B-PER" in r.text
      and "Jobs I-PER" in r.text and "Apple. O" not in r.text.split("\n\n")[0].splitlines()[3],
      r.text[:300])

r = client.get(f"/api/projects/{pid}/export?format=jsonl_legacy", headers=auth)
check("export legacy jsonl", r.status_code == 200
      and json.loads(r.text.splitlines()[0])["labels"][0] == [0, 10, "PER"], r.text[:200])

# --- access control ---
r = client.post("/api/auth/login", data={"username": "bob", "password": "secret123"})
bob_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
r = client.get(f"/api/projects/{pid}/documents", headers=bob_auth)
check("non-member blocked", r.status_code == 403, r.text)
r = client.post(f"/api/projects/{pid}/members", headers=auth,
                json={"username": "bob", "role": "annotator"})
check("add member", r.status_code == 200, r.text)
r = client.get(f"/api/projects/{pid}/documents", headers=bob_auth)
check("member can access", r.status_code == 200, r.text)

# --- deletion ---
r = client.delete(f"/api/projects/{pid}/documents/{doc3}", headers=auth)
check("delete document", r.status_code == 200, r.text)
r = client.post(f"/api/projects/{pid}/documents/bulk-delete", headers=auth,
                json={"document_ids": [doc1]})
check("bulk delete", r.status_code == 200 and r.json()["deleted"] == [doc1], r.text)
r = client.get(f"/api/projects/{pid}/documents", headers=auth)
check("docs removed", r.json()["total"] == 1, r.text)

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    raise SystemExit(1)
print("All smoke tests passed.")
