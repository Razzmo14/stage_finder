# Progress Log

<!--
This file is agent-agnostic: Codex, Claude Code, OpenHands, and other coding
agents can use it. Read it at session startup and update it before handoff
through the repository's agent instructions; no agent updates it
automatically.
-->

This is the repository-local session progress log for Stage Finder. Read it
at session startup and update it before handoff; agents do not update it
automatically.

## Current Verified State

- Repository root: /home/razzmo/projects/stage_finder
- Standard startup path: ./init.sh (full verification: uv sync, npm install,
  ruff, pytest, npm run build, cargo check)
- Standard verification path: ./init.sh (same; SKIP_CARGO_CHECK=1 skips the
  Rust core)
- Current highest-priority unfinished feature: llm-003 (OpenRouter client:
  keychain key, live model catalog, capability-aware structured output,
  usage tracking)
- Current blocker: none

## Session Log

### Session 002

- Date: 2026-10-28
- Goal: Implement feature skel-001 (Phase 1 skeleton), then continue in
  priority order.
- Completed:
  - skel-001 (passing):
    - backend/: FastAPI sidecar, session-token middleware (401 on every
      request without the per-launch Bearer token, including /health),
      pydantic-settings config, uvicorn entry point (`python -m app`).
    - src/: React 18 + Vite + Tailwind skeleton: sidebar with the planned
      navigation, status bar polling the authenticated /health endpoint via
      the Tauri commands.
    - src-tauri/: Tauri 2 core, minimal per architecture: random session
      token (48 alphanumerics, memory only), free-port allocation, sidecar
      spawn via uv with supervision/restart-on-crash, kill on exit,
      get_backend_url/get_session_token commands, strict CSP, generated
      icon set.
    - README.md (setup/dev/verification), .env.example (no secrets allowed),
      .gitignore.
  - db-002 (passing):
    - backend/app/db/models.py: 12 tables per docs/ARCHITECTURE.md (Profile,
      Experience, Education, Project, Document, SearchCriteria, Offer with
      dedup hash + embedding, MatchResult, Application, LLMUsage, EventLog,
      ModelConfig). JSON columns for list/dict fields; no secrets stored.
    - Alembic wired to the SQLModel metadata (backend/alembic.ini, alembic/,
      initial revision a1dc86066505); migrations run automatically at sidecar
      startup (app/db/migrate.py + lifespan hook).
    - backend/tests: auth (8), migrations (3), model CRUD round-trips with FK
      protection checks (5).
  - System prerequisite resolved this session: installed the Tauri Linux
    libraries (libwebkit2gtk-4.1-dev etc.) so cargo check can run.
- Verification run: ./init.sh full run passed (ruff clean, pytest 16 passed,
  tsc && vite build, cargo check). Live smoke tests: sidecar 401 without
  token / 200 with token; first run created and migrated the SQLite DB.
- Evidence captured: feature_list.json (skel-001, db-002 evidence arrays),
  this file.
- Commits: 7de9f13 (skel-001) + this session's db-002 commit.
- Known risk or unresolved issue:
  - The desktop app spawns the sidecar via `uv run` from the project
    directory (dev-mode); release packaging (PyInstaller externalBin) is
    feature pkg-016. `tauri build` outputs are not verifiable until then.
  - The GUI itself (`npm run tauri dev`) has not been exercised end to end in
    this session (no display in the agent environment); the health poll and
    commands are verified at the HTTP/cargo level instead.
  - sqlite-vec and the embedding model-name tables land with match-006.
- Next best step: implement llm-003 (OpenRouter client behind the
  LLMProvider interface: keychain-stored API key via keyring, live model
  catalog GET /api/v1/models with caching, capability-aware structured
  output with fallback, usage/cost recording in LLMUsage/EventLog per ADR
  0002). Contract tests must mock the OpenRouter endpoint; the real API
  must never be called from tests.

### Session 001

- Date: 2026-10-28
- Goal: Adapt the agent-workflow template to the Stage Finder specification
  (local-first desktop app that automates job/internship applications with an
  LLM and mandatory user confirmation before any send).
- Completed:
  - docs/PRODUCT.md rewritten for Stage Finder (product description, hard
    no-auto-send rule, core features, tech requirements, constraints).
  - docs/ARCHITECTURE.md rewritten with the planned architecture (Tauri 2
    minimal Rust core, React renderer, FastAPI sidecar, session-token
    authentication, data flow, storage plan).
  - docs/decisions/: ADR 0001 session-token sidecar, ADR 0002 OpenRouter
    capability-aware integration, ADR 0003 nothing is ever sent
    automatically.
  - feature_list.json: 17 features derived from the spec's Phase 1/2/3 plan,
    each with concrete verification steps; all not_started.
  - init.sh: template-only verification while no code exists; full
    verification (uv/pytest/ruff, npm build, cargo check) activates when the
    skeleton lands.
- Verification run: ./init.sh (template-only) passed; feature_list.json is
  valid JSON.
- Evidence captured: init.sh output, session 001 entry in this file.
- Commits: none yet (no git repository initialized).
- Files or artifacts updated: docs/PRODUCT.md, docs/ARCHITECTURE.md,
  docs/decisions/0001..0003, feature_list.json, init.sh, PROGRESS.md.
- Known risk or unresolved issue: product name assumed as "Stage Finder"
  (from the repository name) and is used in docs and the planned bundle
  identifier; no implementation exists yet -- everything above is
  specification/planning artifacts only. A partial code scaffold was created
  and then fully removed per user request (template adaptation only).
- Next best step: implement feature skel-001 (Tauri 2 + React/Vite/Tailwind
  frontend, minimal Rust core spawning the FastAPI sidecar with the
  per-launch session token, health check, README with setup instructions and
  .env.example).
