"""Live test of the NER auto-annotation flow: train on annotated docs, then
verify model-suggested spans appear on unannotated docs for review."""
import io
import json
import os
import tempfile
import time

tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "test.db")
os.environ["MODELS_DIR"] = os.path.join(tmp, "models")
os.environ["NER_TRAINING_ITERATIONS"] = "20"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

client.post("/api/auth/register", json={
    "username": "alice", "email": "a@x.com", "password": "secret123"})
token = client.post("/api/auth/login",
                    data={"username": "alice", "password": "secret123"}).json()["access_token"]
auth = {"Authorization": f"Bearer {token}"}

pid = client.post("/api/projects", headers=auth, json={
    "name": "ML test", "auto_annotate_threshold": 5}).json()["id"]

people = ["John Smith", "Mary Jones", "Peter Brown", "Anna Lee", "Tom Clark",
          "Sara White", "James Hall", "Lucy Green", "Mark King", "Emma Stone"]
orgs = ["Acme Corp", "Globex Inc", "Initech", "Umbrella Co", "Stark Industries",
        "Wayne Enterprises", "Hooli", "Vandelay Industries", "Wonka Ltd", "Cyberdyne Systems"]

annotated_lines = []
for person, org in zip(people, orgs):
    text = f"{person} works at {org} as a senior engineer."
    annotated_lines.append(json.dumps({
        "text": text,
        "entities": [
            {"id": 1, "label": "PER", "start_offset": 0, "end_offset": len(person)},
            {"id": 2, "label": "ORG",
             "start_offset": len(person) + 10,
             "end_offset": len(person) + 10 + len(org)},
        ],
        "relations": [],
    }))
unannotated_lines = [
    json.dumps({"text": f"{person} recently joined {org} in Berlin."})
    for person, org in zip(reversed(people), orgs)
]
payload = "\n".join(annotated_lines + unannotated_lines)
r = client.post(f"/api/projects/{pid}/import?format=jsonl", headers=auth,
                files={"file": ("d.jsonl", io.BytesIO(payload.encode()), "application/json")})
assert r.status_code == 200, r.text
print("imported:", r.json()["imported_documents"], "docs,",
      r.json()["imported_spans"], "spans")

elig = client.get(f"/api/projects/{pid}/auto-annotate/eligibility?task=ner",
                  headers=auth).json()
assert elig["eligible"], elig
print("eligibility:", [(t["name"], t["count"]) for t in elig["types"]])

job = client.post(f"/api/projects/{pid}/auto-annotate", headers=auth,
                  json={"task": "ner"}).json()
print("job started:", job["id"], job["status"])

deadline = time.time() + 600
while time.time() < deadline:
    job = client.get(f"/api/projects/{pid}/jobs/{job['id']}", headers=auth).json()
    if job["status"] in ("completed", "failed"):
        break
    time.sleep(2)

print("job finished:", job["status"])
print("message:", job["message"])
print("metrics:", job["metrics"])
print("annotated docs:", job["annotated_count"])
assert job["status"] == "completed", job

page = client.get(f"/api/projects/{pid}/documents?filter=unreviewed", headers=auth).json()
print("docs needing review:", page["total"])
assert page["total"] > 0, "model produced no suggestions"

doc = client.get(f"/api/projects/{pid}/documents/{page['items'][0]['id']}",
                 headers=auth).json()
model_spans = [s for s in doc["spans"] if s["source"] == "model" and not s["reviewed"]]
print("example doc text:", doc["text"])
print("model spans:", [(doc["text"][s["start_offset"]:s["end_offset"]],) for s in model_spans])
assert model_spans

r = client.post(
    f"/api/projects/{pid}/documents/{doc['id']}/review?action=accept_all", headers=auth)
assert r.status_code == 200 and r.json()["spans"] >= 1, r.text
print("accept_all OK:", r.json())

print("\nNER auto-annotation flow works end-to-end.")
