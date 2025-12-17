# Nexify – AI-Native Ticket Triage Console

Nexify is a small, production-style backend + console UI that simulates how an
AI-powered support team might triage incoming tickets.

It’s built to look and feel like a real internal tool:

- **Django + DRF** backend with JWT auth, multi-tenant organizations, tickets, and audit events  
- **Celery + Redis** background jobs for async triage runs  
- **Postgres + pgvector** for knowledge-base chunks and retrieval (RAG-ready design)  
- **Next.js (App Router) frontend** for agents to see tickets, run AI triage, and approve/reject suggestions

The goal is to demonstrate backend architecture, async pipelines, and a clean
console UI that you can walk through in interviews.

---

## 1. High-Level Architecture

**Core pieces:**

- **API / Backend**
  - Django 5 + Django REST Framework
  - Simple JWT auth (`/api/auth/token/`, `/api/me/`)
  - Multi-tenant models: `Organization`, `Membership`
  - Ticketing: `Ticket`, `TicketEvent`
  - Triage pipeline: `JobRun`, `Suggestion`
  - Knowledge base: `Document`, `DocumentChunk` (with pgvector embeddings)
  - Observability: `django-prometheus`, `/metrics` endpoint

- **Async processing**
  - Celery workers
  - Redis as broker + result backend
  - `run_ticket_triage(job_run_id)` task:
    - Loads the ticket
    - Optionally calls into KB / embeddings
    - Produces a `Suggestion` with:
      - Draft resolution text
      - Optional classification
      - Optional confidence + citations
    - Updates `JobRun` state and logs `TicketEvent`s

- **Frontend**
  - Next.js (App Router) + TypeScript + Tailwind
  - Login page (JWT auth against Django)
  - Console page:
    - Ticket list for a single organization
    - Ticket details panel
    - **Run AI triage** button
    - Suggestion card with resolution text, confidence, approve / reject
    - Recent ticket events

---

## 2. Data Model (short overview)

Main models in `core/models.py`:

- **Organization**
  - Name, created_at
- **Membership**
  - `user`, `organization`, `role` (`admin`, `agent`, `viewer`)
- **Ticket**
  - `organization`, `requester_email`, `subject`, `body`
  - `status` (`open`, `in_progress`, `resolved`)
  - `priority` (`low`, `medium`, `high`, `urgent`)
  - `assigned_team`
  - `created_at`, `updated_at`
- **TicketEvent**
  - `ticket`, `organization`, `job_run`
  - `event_type` (created, status_changed, ai_triage_ran, suggestion_approved, etc.)
  - `actor_type` (`user`, `system`, `ai`, `webhook`)
  - `actor_user`
  - JSON `payload` for details
- **JobRun**
  - Links a triage job to a ticket + org
  - `status` (`queued`, `running`, `succeeded`, `failed`)
  - `idempotency_key` to avoid double-enqueuing
  - `attempt_count`, `last_attempt_at`
- **Suggestion**
  - `organization`, `ticket`, `job_run`
  - `status` (`pending`, `accepted`, `rejected`)
  - `suggested_priority`, `suggested_team`
  - `draft_reply` (resolution text)
  - `classification`, `citations`, `confidence`
  - `metadata`
- **Document / DocumentChunk**
  - Knowledge-base documents and chunks for retrieval
  - `embedding` (pgvector) on chunks, `chunk_index`, `char_start`, `char_end`

---

## 3. Running Nexify with Docker (recommended)

Requirements:

- Docker & docker-compose installed

From the project root:

```bash
# Start Postgres, Redis, and the Django web app container
docker compose up --build


