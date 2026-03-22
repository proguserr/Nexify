# Nexify — AI-Native Ticket Triage Console

**Live demo:** [nexify-cyan.vercel.app](https://nexify-cyan.vercel.app)  
**Login:** `admin` / `password123`

---

## The Problem

Support teams at growing companies waste hours every day on predictable triage decisions. An agent opens a queue of 50 tickets and has to manually read each one to decide who should handle it, how urgent it is, and what the first response should be. This is slow, inconsistent, and burns expensive human time on work that follows repeatable patterns.

## What Nexify Does

Nexify automates the first layer of support triage. When a ticket arrives, the system classifies it, routes it to the right team, assigns a priority, generates a draft reply using Gemini AI, and produces a confidence score — all before a human opens it.

If confidence is high enough the ticket can be auto-resolved. If not, the suggestion surfaces for human review. The agent's job becomes approving or rejecting rather than thinking from scratch.

Every action is logged as an immutable audit event. Nothing is lost.

---

## Live System

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind | Triage console and dashboard |
| API | Django 5, Django REST Framework | HTTP layer, auth, permissions |
| AI | Gemini Flash 2.0 | Ticket classification and draft replies |
| Worker | Celery + Redis | Async job processing |
| Database | PostgreSQL + pgvector | Data storage and vector search |
| Deployment | Railway + Vercel | Production hosting |
| CI/CD | GitHub Actions | Automated testing and linting |

---

## Architecture

```
Ticket arrives (webhook / API)
        ↓
Django validates and stores ticket
        ↓
Agent triggers triage
        ↓
Idempotency check (prevents duplicate jobs)
        ↓
JobRun created → Celery task queued
        ↓
KB searched via pgvector cosine similarity
        ↓
Gemini generates classification + draft reply
        ↓
Confidence scored → auto-resolve or human review
        ↓
Suggestion created → TicketEvents logged
        ↓
Agent approves or rejects
        ↓
Ticket updated → audit trail complete
```

---

## Key Engineering Decisions

**Async triage via Celery?**
LLM calls take 2-5 seconds. Blocking an HTTP request for that duration would degrade the API for all concurrent users. Celery decouples the slow work from the fast HTTP response. The API immediately returns a job ID. The worker processes in the background.

**Idempotency keys on JobRun?**
If an agent double-clicks "Run triage" or a network retry fires, we must not create duplicate LLM calls or duplicate suggestions. The idempotency key enforced at both application level (`select_for_update`) and database level (unique constraint) guarantees exactly-once execution.

**Pgvector instead of a dedicated vector database?**
At current scale, keeping vectors in Postgres eliminates operational complexity — one database to manage, one connection pool, one backup strategy. A dedicated vector database like Pinecone adds value at millions of embeddings. Premature optimization otherwise.

**Confidence-based auto-resolution?**
The system should never auto-resolve when it's uncertain. A configurable confidence threshold means the AI acts autonomously only when it has strong signal. Everything below threshold surfaces for human review. This is the core safety guardrail.

**Multi-tenant from day one?**
Multi-tenancy is hard to retrofit. Every model carries `organization_id`. Every query is scoped to it. Every API endpoint validates membership before returning data. Building this correctly from the start means the system can serve multiple organizations without architectural changes.

---

## Data Model

```
Organization
    ├── Memberships → Users (admin / agent / viewer roles)
    ├── Tickets
    │     ├── TicketEvents (immutable audit trail)
    │     ├── JobRuns (triage execution tracking)
    │     │     └── Suggestion (AI output — one per job)
    │     └── Suggestions
    └── Documents
          └── DocumentChunks (with vector embeddings)
```

---

## Security Model

Four independent gates on every request:

1. **Authentication** — JWT token required
2. **Membership** — user must belong to the organization
3. **Data scoping** — all queries filtered by `organization_id`
4. **Object permissions** — role checked against HTTP method

Three independent failures would need to occur simultaneously for a data breach.

---

## API Surface

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/tickets/` | Ingest ticket (public, for webhooks) |
| GET | `/api/organizations/{id}/tickets/` | List tickets with filtering and pagination |
| POST | `/api/tickets/{id}/trigger-triage/` | Run AI triage (requires Idempotency-Key) |
| POST | `/api/.../suggestions/{id}/approve/` | Approve suggestion, apply to ticket |
| POST | `/api/.../suggestions/{id}/reject/` | Reject suggestion |
| POST | `/api/organizations/{id}/kb/retrieve/` | Vector search knowledge base |
| GET | `/api/organizations/{id}/dashboard/` | Triage metrics and analytics |
| GET | `/metrics/` | Prometheus metrics endpoint |

---

## Running Locally

**Prerequisites:** Docker, Docker Compose

```bash
git clone https://github.com/proguserr/Nexify
cd Nexify

# Copy environment variables
cp .env.example .env
# Add your GEMINI_API_KEY to .env

# Start all services
docker compose up --build

# Run migrations
docker compose exec web python manage.py migrate

# Seed demo data
docker compose exec web python manage.py seed_dev

# Frontend
cd frontend
npm install
npm run dev
```

**Users created by seed_dev:**

| Username | Password | Role |
|---|---|---|
| admin | password123 | Admin |
| agent | password123 | Agent |
| viewer | password123 | Viewer |

Visit `http://localhost:3000`

---

## Testing

```bash
# Run full test suite
pytest core/tests -q

# Run with coverage
pytest core/tests --cov=core

# Live Gemini integration test (requires API key)
RUN_GEMINI_LIVE=1 pytest core/tests/test_gemini_live.py
```

Test coverage includes multi-tenant isolation, idempotency, auto-resolution confidence thresholds, retry behavior, and full triage happy path.

---

## What's Next

- Real embedding generation via Google or OpenAI embeddings API (pgvector pipeline is fully wired, stub only needs replacing)
- Celery async mode for production scale (one line change — `.delay()` instead of direct call)
- Webhook ingestion from Zendesk, Intercom, email
- Slack notifications on high-urgency ticket creation
