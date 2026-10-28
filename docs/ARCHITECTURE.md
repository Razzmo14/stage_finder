# Architecture -- Stage Finder (planned)

> Status: target architecture, not yet implemented. Each element lands with
> its feature in `feature_list.json` (the skeleton arrives with `skel-001`).

## System Overview

Stage Finder is a Tauri 2 desktop application with a React/TypeScript
frontend and a Python FastAPI sidecar backend. The Rust core is kept
minimal: window lifecycle, sidecar supervision, session-token generation,
and a few secure commands. All business logic lives in the Python sidecar.

## Layer Diagram

```
+-------------------------------------------------------------+
|                Renderer (React + TypeScript)                 |
|  src/features/: profile, search, offers, applications,       |
|                 review, settings                             |
|  UI state: Zustand | Server state: TanStack Query             |
+-------------------------------------------------------------+
         |  invoke() for get_backend_url / get_session_token
+-------------------------------------------------------------+
|                Tauri Core (Rust, src-tauri/)                  |
|  window lifecycle | sidecar spawn + supervision              |
|  random session token | free-port allocation | commands      |
+-------------------------------------------------------------+
         |  HTTP on 127.0.0.1:<random free port>
         |  Authorization: Bearer <session token>
+-------------------------------------------------------------+
|                Sidecar Backend (FastAPI, /backend)           |
|  app/api: profile, criteria, offers, applications, llm,      |
|           email, settings                                   |
+-------------------------------------------------------------+
         |  service calls
+-------------------------------------------------------------+
|                Services (/backend/app/services)              |
|  job_sources/ | matching/ | letter_generation/ | mailer/     |
|  parsing/ | scheduler/                                     |
+-------------------------------------------------------------+
         |  SQLModel / sqlite-vec
+-------------------------------------------------------------+
|                SQLite database (local file)                 |
+-------------------------------------------------------------+
```

Key invariants:

- The renderer never talks to the network directly for app data; all data
  goes through the sidecar over authenticated localhost HTTP.
- The sidecar binds to 127.0.0.1 only and rejects every request without the
  per-launch session token.
- The Rust core contains no business logic and persists nothing.
- No secrets (API keys, OAuth tokens) are stored in plain text or in the
  database; they live in the OS keychain (keyring / Tauri keychain plugin).

## Tauri Core (`src-tauri/`)

Responsibilities:

- Generate a random session token at launch (never persisted).
- Allocate a free port on 127.0.0.1 and spawn the Python sidecar with the
  port and the token, then health-check it and restart it on crash; kill it
  on app close.
- Expose the backend URL and session token to the renderer via two commands.
- Strict CSP, minimal capabilities in `tauri.conf.json`.

Key invariant: no business logic in Rust.

## Renderer (`src/`)

React + Vite + Tailwind CSS + shadcn/ui, React Router or TanStack Router for
navigation. Features live in `src/features/` (profile, search, offers,
applications, review, settings). Zustand stores UI state; TanStack Query
manages all sidecar data with a fetch wrapper that injects the session token.

Key invariant: renderer code never sees raw secrets; it only forwards the
in-memory session token.

## Sidecar Backend (`/backend`)

FastAPI application started by Tauri on a random port.

- `app/api` -- routers: profile, criteria, offers, applications, llm, email,
  settings.
- `app/core` -- config (Pydantic Settings), security (session-token
  middleware), logging.
- `app/db` -- SQLModel models, engine, session, Alembic migrations.
- `app/services` -- job_sources/ (JobSource plugin interface: France Travail,
  Adzuna, Jooble), matching/ (embeddings + LLM re-ranking),
  letter_generation/ (adaptation + grounding check), mailer/ (Gmail API,
  Microsoft Graph, SMTP/IMAP), parsing/ (PDF/DOCX extraction), scheduler/
  (APScheduler jobs).
- `app/llm` -- LLMProvider abstraction (openrouter default, anthropic, openai,
  ollama), live model catalog (GET /api/v1/models, cached), capability
  detection (supported_parameters), prompts, structured-output schemas.

Key invariant: providers and sources are behind interfaces; no LangChain;
direct SDK calls only.

## Authentication

1. Tauri generates a cryptographically random session token at launch.
2. Tauri passes it to the sidecar (environment variable) and to the
   frontend (invoke command).
3. The FastAPI middleware rejects any request without
   `Authorization: Bearer <token>` (401), including on `/health`.
4. Token and port are never written to disk or logs.

## Data Flow (primary: offer to application)

1. The user saves SearchCriteria; the scheduler or a manual run queries each
   enabled JobSource.
2. Offers are normalized to the common Offer schema, deduplicated (hash +
   fuzzy match), and stored.
3. Matching stage 1 computes embedding similarity; stage 2 asks the LLM for
   a structured MatchResult (score, rationale, matched/missing skills, red
   flags).
4. Letter generation produces a structured output (letter, email subject,
   email body, claims) from profile + base letter + offer.
5. The claim-verification step flags unsupported claims.
6. The review screen shows the offer, the letter diff, and flags; the user
   edits, approves, saves as draft, or rejects.
7. On explicit confirmation only, the mailer sends (or creates a draft in
   the mailbox); the Application status and the EventLog are updated.
8. Tracking views and reminders read from the Application table.

## Build Pipeline (planned)

1. `uv sync` installs the Python backend environment.
2. `npm install` installs the frontend.
3. `npm run build` bundles the renderer with Vite to `dist/`.
4. `cargo build` / `tauri build` compiles the Rust core.
5. For releases, the Python sidecar is frozen with PyInstaller into
   `stage-finder-backend[-<target-triple>]` and declared as `externalBin` in
   `tauri.conf.json` (one binary per OS/architecture).

## Data Storage (planned)

SQLite database file in the user's data directory:

```
{data-dir}/stage-finder/
  stage-finder.db          # SQLModel tables (profile, offers, applications...)
  vec_* tables             # sqlite-vec embeddings (+ embedding model name)
```

Main tables: Profile, Experience, Education, Project, Document,
SearchCriteria, Offer (raw payload + dedup hash + embedding), MatchResult,
Application (status, timestamps, follow-up), LLMUsage/EventLog (model,
tokens, cost per request), ModelConfig (per-task model assignment,
routing/privacy options).
