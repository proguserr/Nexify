# Nexify – AI-native Ticket Triage Console

Nexify is a small but realistic project with a **Django + Celery + Postgres/pgvector** backend and a **Next.js console** on top.

The goal is to model how a support team might triage tickets with an AI assistant, using the kind of stack and patterns you’d expect in a production environment.

---

## 1. What Nexify does

At a high level:

- Stores **support tickets** for an organization (subject, body, priority, assigned team, status).
- Runs an **async triage job** that:
  - inspects a ticket,
  - proposes a new priority + owning team,
  - drafts a reply,
  - records the whole thing as a **Suggestion** row.
- Lets an agent:
  - review the suggestion in a Next.js **console UI**,
  - approve or reject it,
  - and write the result back to the ticket.

Everything is wired as in a typical backend system: REST API, background worker, Redis, Postgres/pgvector, and a separate frontend.

---

## 2. Why I built this

- Simulating production grade environment!

Nexify is my way to show that I:

- break a problem into **services** (API, worker, data store, UI),
- use **background jobs** for long-running work,
- keep code **observable** and **deployable** (metrics, Docker, health checks),
- and ship a UI that talks to that backend over clean HTTP boundaries.

If you want to go deeper, you can clone the repo and run the full stack locally.

---

## 3. LLM & RAG (how the AI piece works)

The triage flow is a **RAG-style pipeline** implemented in `core/tasks.py` and `core/llm_client.py`:

1. **Retrieve** – Ticket subject + body are used as the query; `search_kb_chunks_for_query` returns the top‑k **KB chunks** for that organization (pgvector similarity when chunks have embeddings).
2. **Classify** – `classify_ticket_with_llm` sends the ticket text and KB snippets to an LLM and expects **strict JSON** (category, team, priority, draft reply, optional confidence and `auto_resolve`).
3. **Persist** – A `Suggestion` is created with **citations** from the KB hits; `metadata` includes `category` and a truncated `raw_output` when available.
4. **Auto-resolve (optional)** – If the model sets `auto_resolve: true` **and** `confidence` is at least **0.85**, the ticket is updated (priority, assigned team, status `resolved`) and an `AUTO_RESOLUTION_APPLIED` event is recorded.

### Google Gemini (default when configured)

For demos and hosted setups, **Gemini** is used when `GEMINI_API_KEY` is set (unless you force another provider). Get a key from [Google AI Studio](https://aistudio.google.com/). The free tier (rate limits such as requests per minute and tokens per day) is usually enough for development.

Environment variables (see also `.env.example`):

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Required for Gemini. When set, triage defaults to Gemini unless overridden. |
| `GEMINI_MODEL` | Optional; default `gemini-2.0-flash`. |
| `LLM_PROVIDER` | `gemini` – force Gemini; `ollama` – force local Ollama; `heuristic` – **no LLM call**, keyword rules only (offline / CI-friendly). |
| `RUN_GEMINI_LIVE` | Set to `1` to enable the optional pytest that calls the **real** Gemini API (otherwise skipped; avoids quota in CI). |

If the LLM call fails (network, quota, invalid JSON), triage **falls back** to the built-in heuristic classifier and sets `metadata.llm_fallback` and `metadata.llm_error`.

**Secrets and restarts:** Put `GEMINI_API_KEY` (and optional `LLM_PROVIDER`, `GEMINI_MODEL`) in a **`.env`** file in the project root—**not** in `.env.example` (that file is a template and may be committed). Django loads `.env` via `config/settings.py`. After editing `.env`, **restart** `runserver` / gunicorn and any **Celery worker**. With **Docker Compose**, keep the same variables in `.env` beside `docker-compose.yml`; the `web` and `worker` services pass them through. If a key was ever committed or pasted into chat, **rotate it** in Google AI Studio.

### Ollama (local)

Set `LLM_PROVIDER=ollama` and run Ollama locally. Use `OLLAMA_BASE_URL` and `OLLAMA_MODEL` as needed. If `GEMINI_API_KEY` is **not** set and `LLM_PROVIDER` is unset, the client defaults to **Ollama** (previous behavior).

---

## 4. Architecture

### Components

- **API service (Django REST Framework)**
  - JWT auth: `/auth/token/`, `/me`
  - Ticket CRUD and listing
  - Triage endpoints:
    - trigger job,
    - fetch latest suggestion,
    - approve / reject
  - Prometheus metrics endpoint via `django-prometheus`

- **Worker (Celery)**
  - Consumes triage jobs from Redis
  - Runs the RAG + LLM / rules engine pipeline
  - Writes **Suggestion** rows and `TicketEvent` audit rows

- **Data**
  - **Postgres 16 + pgvector** for:
    - tickets and suggestions,
    - ticket events,
    - knowledge-base documents and embeddings

- **Frontend (Next.js 16, App Router)**
  - Login screen with a **session inspector** panel showing the raw `/me` response
  - Ticket list + detail view
  - “Run AI triage” button and suggestion review panel
  - Approve flow that calls the backend and updates ticket state in the UI

- **Observability**
  - `django-prometheus` DB backend + middleware
  - `/metrics` endpoint ready for Prometheus scraping

### Data model (simplified)

- **Ticket**
  - `id`, `organization`, `requester_email`
  - `subject`, `body`
  - `priority` (`low` | `medium` | `high` | `urgent`)
  - `assigned_team`, `status`
  - timestamps

- **Suggestion**
  - `id`, `ticket`, `job_run`
  - `suggested_priority`, `suggested_team`
  - `draft_reply`
  - `metadata` (LLM / RAG internals)
  - `status` (`pending` / `accepted` / `rejected`)
  - timestamps

- **TicketEvent**
  - Tracks actions like:
    - `TRIAGE_ENQUEUED`
    - `SUGGESTION_CREATED`
    - `SUGGESTION_APPROVED`
    - `SUGGESTION_REJECTED`
  - Used as an audit log for what happened to each ticket.

### Request flow

1. **Login**
   - Frontend POSTs username/password → `/auth/token/`.
   - Stores the `access` token in `localStorage` (`nexify_access`).
   - Calls `/me` to show the current user and org in the session inspector panel.

2. **List tickets**
   - Console page calls  
     `GET /organizations/{ORG_ID}/tickets/?ordering=-id`
   - Renders a ticket list on the left; clicking a ticket opens its details.

3. **Run triage**
   - Console calls  
     `POST /tickets/{ticket_id}/trigger-triage/`  
     with an `Idempotency-Key` header to avoid duplicate jobs.
   - Backend enqueues a Celery job and records a `TRIAGE_ENQUEUED` event.

4. **Worker triage job**
   - Fetch ticket.
   - Run embedding + vector search over the KB.
   - Call the LLM client (Ollama/local or hosted).
   - Write a `Suggestion` row and a `SUGGESTION_CREATED` event.

5. **Review suggestion**
   - Console polls  
     `GET /organizations/{ORG_ID}/tickets/{ticket_id}/suggestions/`.
   - Picks the latest suggestion and displays:
     - proposed team,
     - proposed priority,
     - draft reply,
     - status badge.

6. **Approve**
   - Console calls  
     `POST /organizations/{ORG_ID}/tickets/{ticket_id}/suggestions/{suggestion_id}/approve/`.
   - Backend applies the changes back to the `Ticket` and logs `SUGGESTION_APPROVED`.

---

## 5. Tech stack

**Backend**

- Python 3.11  
- Django 5  
- Django REST Framework  
- Postgres 16 + `pgvector`  
- Celery + Redis  
- JWT auth via `rest_framework_simplejwt`  
- `django-prometheus` for metrics  

**Frontend**

- Next.js 16 (App Router)  
- React 18 + TypeScript  
- Tailwind-style utility classes for styling  
- Deployed to Vercel  

**Infra / tooling**

- Docker & Docker Compose for local dev
- Gunicorn for production WSGI
- Black, Ruff, pytest for the backend

---

## 6. Running Nexify locally

You’ll run the **backend via Docker Compose**, and the **frontend via the Next.js dev server**.

### 6.1. Backend (Django + Celery + Postgres + Redis)

From the repo root:

```bash
docker compose up --build


The API will be reachable at:'http://localhost:8000/api/'


####Database / admin setup

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

###6.2. Frontend (Next.js console)

```bash

npm install
npm run dev
```
Visit: `http://localhost:3000`

#Project status

Right now:

•Frontend is deployed on Vercel as a UI demo.Backend is fully dockerized and intended to run locally (or on any platform that supports Docker).End-to-end flow (login → list tickets → run triage → approve suggestion) works when both services are running.

I’m deliberately keeping the backend self-hosted instead of paying for a managed deployment. Anyone who wants to explore the system more deeply can clone the repo and run docker compose up to start the full stack.


Demo link: `https://nexify-cyan.vercel.app/`





