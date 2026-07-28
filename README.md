# GraphMind

**NER & RE annotation for knowledge graphs**

A self-hosted annotation platform purpose-built for **Named Entity
Recognition** and **Relation Extraction** — the two ingredients for building
**knowledge graphs** from text. It runs entirely on your own local server,
with built-in **auto-annotation**: once you have annotated enough examples,
one button trains a model in the background and pre-annotates the rest of your
corpus for review. Entities become nodes, relations become edges.

## Highlights

- **Standard JSONL file formats** — import/export JSONL with `entities` +
  `relations` (one JSON object per line), legacy span `labels` JSONL, and
  plain text; export CoNLL 2003. Plain, documented formats with no lock-in.
- **Auto-annotation**
  - *NER*: a spaCy pipeline is trained on your human annotations.
  - *Relation Extraction*: a BERT-family classifier (DistilBERT by default;
    `bert-base-uncased` or `SpanBERT/spanbert-base-cased` via `RE_BASE_MODEL`)
    is fine-tuned on your annotated relations. GPU auto-detection: NVIDIA
    CUDA → Apple Silicon MPS → CPU.
  - The **Auto-Annotate button unlocks** when at least one label type reaches
    the per-project threshold of human annotations (default 20, configurable
    in project Settings).
  - Model suggestions are stored as `source: model`, flagged **needs review**,
    and never overwrite human work. Review them per item, per document
    (Accept/Reject all), or via the *Needs review* document filter.
- **Rules (pre-population without training)** — on the **Rules** page:
  - *NER keyword rules*: map a keyword to an entity type and tag **every
    occurrence across the whole corpus** in one click (case-sensitivity and
    whole-word options; idempotent re-runs). Pure Python — needs no ML deps.
    Rule spans are stored as `source: rule`, reviewed, and count as training data.
  - *Relation rules (embedding similarity)*: associate two entity types and a
    relation with an **example sentence** (e.g. *PERSON —sibling_of→ PERSON*,
    "is the sibling of"). The example is embedded **once** (cached on the rule)
    with a BERT-family sentence encoder. Applying scans every ordered
    entity-type pair within a distance window, embeds the connecting text, and
    links pairs whose cosine similarity clears the threshold. Proposed
    relations are `source: rule`, flagged **needs review**, with the similarity
    stored as confidence.
- **Built for large corpora** — server-side pagination everywhere, indexed
  queries, background training jobs that never block the UI; annotations are
  stored as character offsets into immutable document text, so spans can
  never drift or misalign.
- **Instant auto-save** — every span/relation action is persisted to the
  server database the moment it happens; navigating documents never loses work.
- **Easy sample removal** — delete a document from the annotation screen or
  delete in bulk from the document table.
- **Multi-user** — JWT logins, per-project membership and roles
  (admin/annotator), the first registered account becomes server admin.

## Architecture

```
frontend/   React + TypeScript (Vite) single-page app
backend/    FastAPI + SQLAlchemy
            ├── app/routers/   REST API (auth, projects, documents, labels,
            │                  annotations, import/export, auto-annotate, rules)
            ├── app/rules_engine.py  keyword (gazetteer) NER rules — no ML deps
            └── app/ml/        background job queue + spaCy NER trainer
                               + transformers RE trainer
                               + sentence-embedding relation rules
database    PostgreSQL (production) or SQLite (development)
```

The frontend builds into `backend/static` and is served by FastAPI, so in
production you run **one server process** on one port.

---

## One-step installers

### Windows (server or desktop)

Right-click **`install_windows.bat`** → *Run as administrator*. The installer:

1. finds Python 3.10+ (installs Python 3.12 via winget if missing),
2. creates the virtual environment and installs all server dependencies,
3. optionally installs the auto-annotation ML stack — and if an **NVIDIA GPU**
   is detected, automatically installs the CUDA build of PyTorch,
4. generates `backend\.env` with a fresh secret key (SQLite by default;
   switch to PostgreSQL later by editing one line),
5. builds the frontend (installs Node.js via winget if missing),
6. opens TCP 8000 in Windows Firewall,
7. optionally registers a scheduled task so the server **starts with Windows**.

Then run **`start_server.bat`** (or reboot, if auto-start was enabled) and
open `http://<server-name>:8000` from any machine on the network.

Unattended install: `install_windows.bat -WithML -AutoStart`

### macOS (Apple Silicon M1–M4 and Intel)

```bash
./install_mac.sh            # interactive; or --with-ml / --no-ml
```

Then double-click **`start_server.command`** (or run it from a terminal) —
it starts the server and opens `http://localhost:8000` in your browser.
On M-series Macs, relation-extraction training automatically uses the
**Apple GPU (MPS)**; spaCy NER trains efficiently on CPU. Set `PORT=8765`
before launching to use a different port.

---

## Quick start (development, any OS)

```bash
# Backend
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # API server (SQLite default)
.venv/bin/pip install -r requirements-ml.txt     # optional: auto-annotation
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal, hot reload, proxies /api to :8000)
cd frontend
npm install
npm run dev          # open http://localhost:5173
```

Open the app, click **"First time setup: create admin account"** — the first
account registered becomes the administrator. After that, registration closes
and the admin creates user accounts (Project → Members page), unless you set
`ALLOW_OPEN_REGISTRATION=true`.

Run the test suites:

```bash
cd backend
.venv/bin/python smoke_test.py       # 31 API checks
.venv/bin/python smoke_test_ml.py    # live NER train + auto-annotate flow (needs spaCy)
.venv/bin/python smoke_test_rules.py # keyword rules + embedding relation rules
```

---

## Production deployment on a Windows server

### 1. Install prerequisites

- **Python 3.10–3.12** (python.org installer; check *Add python.exe to PATH*)
- **Node.js 20+** (only needed once, to build the frontend)
- **PostgreSQL 15+** (postgresql.org Windows installer)

### 2. Create the database

In *SQL Shell (psql)*:

```sql
CREATE USER annotator WITH PASSWORD 'choose-a-strong-password';
CREATE DATABASE annotation OWNER annotator;
```

### 3. Set up the backend

```bat
cd C:\annotation\backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -r requirements-ml.txt
```

> **GPU note:** if the server has an NVIDIA GPU, install the CUDA build of
> PyTorch *before* `requirements-ml.txt`:
> `.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu121`
> Training auto-detects the GPU; otherwise it runs on CPU (the defaults —
> spaCy NER and DistilBERT RE — are sized to be CPU-trainable).

Create `C:\annotation\backend\.env` (copy `.env.example`):

```env
DATABASE_URL=postgresql+psycopg2://annotator:choose-a-strong-password@localhost:5432/annotation
SECRET_KEY=<output of: python -c "import secrets; print(secrets.token_hex(32))">
DEFAULT_AUTO_ANNOTATE_THRESHOLD=20
```

### 4. Build the frontend (once per upgrade)

```bat
cd C:\annotation\frontend
npm install
npm run build
```

This writes the app into `backend\static`, which FastAPI serves.

### 5. Run the server

```bat
cd C:\annotation\backend
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Annotators on the network open `http://<server-name>:8000`, sign in, and
work. All annotations save to PostgreSQL instantly. (Open TCP 8000 in
Windows Defender Firewall: *inbound rule → port 8000 → allow*.)

> Keep `--workers 1` (the default). The in-process training job queue runs
> inside the server process; one worker guarantees a single training queue.
> The async server easily handles a team of annotators.

### 6. Run as a Windows service (recommended)

Using [NSSM](https://nssm.cc) (simplest reliable way):

```bat
nssm install AnnotationServer C:\annotation\backend\.venv\Scripts\uvicorn.exe ^
  "app.main:app --host 0.0.0.0 --port 8000"
nssm set AnnotationServer AppDirectory C:\annotation\backend
nssm start AnnotationServer
```

The service starts with Windows and restarts on failure. Training jobs
interrupted by a restart are marked *failed* and can simply be re-run.

---

## Working with the platform

### Typical workflow

1. **Create a project**, define entity types (with colors + keyboard hotkeys)
   and relation types on the **Labels** page.
2. **Import** your corpus (Documents → Import): JSONL (with entities/relations),
   one-doc-per-line text, or whole-file text. On JSONL import, entities,
   relations, and metadata carry over and label types are created automatically.
3. **Annotate**: select text → pick the entity type (mouse, hotkey, or number
   key). Click an entity tag → *Add relation* → click the target entity →
   pick the relation type. Arrow keys move between documents; everything
   saves instantly.
4. **Rules** (📐 page) — optional, pre-populate before/instead of training:
   - *Keyword rules*: add `keyword → entity type` (e.g. `Aspirin → DRUG`) and
     click **Apply to all documents** to tag every occurrence corpus-wide.
   - *Relation rules*: pick head/tail entity types and a relation, write one
     example sentence (e.g. "is the sibling of"), set a similarity threshold,
     and **Apply** — pairs whose connecting text matches the example are linked
     for review. The example is embedded once when you save the rule.
5. **Auto-Annotate** (🤖 page): progress bars show how close each label type
   is to the threshold. When a type crosses it, press **Train & Auto-Annotate**
   — the model trains in the background (live progress + held-out P/R/F1),
   then annotates every untouched document.
6. **Review**: the *Needs review* filter walks you through model- and
   rule-suggested annotations; accept/reject per item or per document. Accepted
   suggestions become training data for the next auto-annotation round.
7. **Export** as JSONL / legacy span JSONL / CoNLL 2003 for downstream model
   training or knowledge-graph construction.

### File formats

Import/export JSONL (one JSON object per line):

```json
{"text": "Steve Jobs founded Apple.",
 "entities": [{"id": 1, "label": "PER", "start_offset": 0, "end_offset": 10},
              {"id": 2, "label": "ORG", "start_offset": 19, "end_offset": 24}],
 "relations": [{"id": 1, "from_id": 1, "to_id": 2, "type": "works_at"}]}
```

A legacy span format `{"text": ..., "labels": [[0, 10, "PER"]]}` is accepted
on import and available on export. Extra JSON keys are preserved as document
metadata. API docs (Swagger): `http://<server>:8000/docs`.

### Configuration reference (.env)

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///<backend>/annotation.db` | PostgreSQL/SQLite connection string |
| `SECRET_KEY` | — | JWT signing key (set a random 64-char hex) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 720 | Login session length |
| `ALLOW_OPEN_REGISTRATION` | false | Allow self-service signup after first user |
| `DEFAULT_AUTO_ANNOTATE_THRESHOLD` | 20 | Default per-type unlock threshold for new projects |
| `MODELS_DIR` | `<backend>/trained_models` | Where per-project trained models are stored |
| `NER_BASE_MODEL` | `blank:en` | spaCy base (`blank:<lang>` or an installed pipeline) |
| `NER_TRAINING_ITERATIONS` | 30 | spaCy training epochs |
| `RE_BASE_MODEL` | `distilbert-base-uncased` | HF model for relation extraction |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Sentence encoder for relation rules |
| `DEFAULT_RELATION_RULE_THRESHOLD` | 0.55 | Default cosine threshold for new relation rules |

## License

Copyright © 2026 PatternPredix, LLC. All Rights Reserved.

Proprietary and confidential. See [LICENSE](LICENSE). No use, copying,
modification, or distribution is permitted without the prior written
permission of PatternPredix, LLC.
