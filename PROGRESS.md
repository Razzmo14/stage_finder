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
- Standard startup path: ./init.sh (uv sync, npm install, ruff, pytest,
  tsc+vite build, cargo check)
- Standard verification path: ./init.sh (same; SKIP_CARGO_CHECK=1 skips the
  Rust core)
- Features skel-001 through pkg-016 (Phase 1 and Phase 2): passing with
  evidence in feature_list.json. release-017: in_progress (signing and
  auto-update need maintainer identities + a published update server).
- Current blocker: none for local work; release-017 remains partially
  verified for external reasons (signing identities), see below.

## Session Log

### Session 003

- Date: 2026-10-28
- Goal: "Fais l'app en entier" — implement the whole app from feature_list
  in priority order.
- Completed (each feature verified with mocked external endpoints, evidence
  in feature_list.json, one commit per feature):
  - llm-003: LLMProvider protocol, OpenRouter provider (OpenAI SDK at
    openrouter base_url, data_collection=deny), live model catalog with
    cache and capability detection, capability-aware structured output
    (native response_format / JSON fallback with validation-error retry),
    usage+cost recording in LLMUsage; keychain-only API key with masked
    display. Settings screen (key, catalog, test call).
  - profile-004: profile CRUD (identity, skills, experiences, education,
    projects, base letter + style rules), CV import PDF (pdfplumber) /
    DOCX (python-docx), LLM extraction into a structured draft the user
    confirms; parsing tested with a hand-built valid PDF fixture.
  - search-005: JobSource interface; France Travail source (OAuth2 client
    credentials, recorded-fixture contract tests); ingestion with hash +
    source-id + fuzzy dedup; criteria CRUD; POST /search/run; offers API.
    Search & Offers screen.
  - match-006: pluggable embeddings (local deterministic HashingEmbedder
    default, API embedder), stage-1 cosine ranking with stored embeddings
    + model name, stage-2 LLM structured MatchJudgement (score/rationale/
    matched/missing/red flags); offers sorted by score; sqlite-vec
    installed and loadable.
  - letter-007: LetterOutput structured schema (letter, subject, body,
    claims) with anti-invention prompt; letter language follows the offer
    (fr/en detection); grounding check behind a protocol (heuristic default
    + LLM verifier) flagging unsupported claims; POST /letters/generate
    creates an Application in pending_review.
  - review-008: review API (queue, inline edits that never change status,
    approve/reject/save-for-later with EventLog; HARD RULE test: no route
    can send, no sent status reachable); streamed regeneration
    (LLMProvider.stream, text/plain chunks, persisted + logged); Review
    screen: side-by-side, word-level diff, flagged claims highlighted,
    streamed regeneration, approve/reject/save.
  - mail-009: Gmail OAuth2 (PKCE, S256, keychain-only tokens), deliver()
    as the single mailbox gateway: drafts by default, direct send only
    with the opt-in setting AND explicit confirmation, daily send limit;
    new appsetting table (migration b2f000000002); Settings mail section
    + final confirmation dialog in the Review screen.
  - track-010: applications list/kanban/timeline; transitions update
    updated_at + EventLog; follow-up dates displayed. Applications screen.
  - sources-011: Adzuna + Jooble sources behind the JobSource interface,
    contract tests with recorded fixtures, cross-source dedup test.
  - mail-012: Microsoft Graph (PKCE, drafts via /me/messages, send via
    /me/sendMail) and SMTP/IMAP fallback (STARTTLS + retry with backoff,
    drafts via IMAP APPEND to Drafts); account selection in settings and
    deliver(); UI account selector.
  - sched-013: APScheduler started at startup, stable job IDs
    (idempotent registration across restarts), periodic searches over
    enabled criteria, due follow-ups with idempotent per-day
    notifications; HARD RULE test: the scheduler modules reference
    neither the mailer nor deliver(); UI banner + web Notification API;
    settings helpers moved to app/services/settings.py.
  - providers-014: Anthropic (httpx Messages API), direct OpenAI (native
    structured), Ollama (local-only, streaming); provider registry with
    settings-based switching + capability flags; monthly budget cap
    blocking generations with a clear message; UI provider selector and
    budget field.
  - i18n-015: i18next FR/EN, 164 aligned keys, all screens migrated to
    t(), sidebar language switcher persisted in localStorage; audit shows
    no remaining hardcoded user-facing strings.
  - pkg-016 (in_progress): PyInstaller onefile sidecar (alembic + pdfminer
    data, sqlite_vec native lib), frozen-mode migration support,
    boot-verified (401/200 + migrations inside the binary);
    scripts/build-sidecar.sh; externalBin declared in tauri.conf.json;
    release spawn implemented in the Rust core; CI matrix workflow
    authored.
  - release-017 (in_progress): docs/USER.md (full user guide),
    docs/RELEASE.md (signing + auto-update steps), updater scaffolding in
    tauri.conf.json (inactive, placeholder keys).
- Verification run (session 003, final): ./init.sh full run passed
  (ruff clean, pytest 118 passed, tsc + vite build, cargo check); the
  real app launched via `npm run tauri dev`: window opened, sidecar
  spawned, migration b2f000000002 applied, supervisor reported
  "sidecar healthy on 127.0.0.1:46801". The PyInstaller sidecar binary
  was also boot-verified standalone.
- Evidence captured: feature_list.json (evidence arrays per feature,
  118 tests), this file, session-handoff.md.
- Commits: 23ba793, 2104e7a, 7a9d88e, 737ec40, 41672d6, 109e5ac,
  61c599d, d8ab041, f88d848, ab7a675, d2cf5a9, b32760e, 84e81b5,
  c99bdb9, edcb076 (plus the earlier 7de9f13, af10234, 33e8033 from
  sessions 001/002).
- Known risk or unresolved issue:
  - pkg-016: DONE — CI matrix succeeded on GitHub Actions for the three
    OSes (run 40694536137, installer artifacts uploaded); the workflow now
    also publishes a GitHub Release when a v* tag is pushed.
  - release-017: signed installers and an actual update test require the
    maintainer's signing identities (Windows certificate, Apple Developer
    identity, Tauri updater key pair) and a published release + update
    server. Steps documented in docs/RELEASE.md.
  - The desktop notification for follow-ups uses the Web Notification
    API inside the webview; on platforms where it is unavailable the
    in-app banner still shows.
  - Embeddings default to a local deterministic hashing embedder (no
    model download, offline); sentence-transformers/API embedders plug in
    via the EmbeddingProvider interface.
- Next best step: run the CI matrix for pkg-016 (needs a GitHub remote),
  then release-017 signing + auto-update against a published release.
  Optional follow-ups: per-task model assignment UI (ModelConfig table
  exists), application-form offers (pre-fill/clipboard/open URL, MVP
  per ADR 0003), data export/deletion endpoints (GDPR section of the
  spec).

### Session 002

- Date: 2026-10-28
- Goal: Implement feature skel-001 (Phase 1 skeleton), then continue in
  priority order.
- Completed: skel-001 (skeleton: FastAPI sidecar with session-token auth,
  React/Vite/Tailwind renderer, minimal Tauri core with sidecar
  supervision; verified live) and db-002 (SQLModel + Alembic, migrations
  at startup). Exposed and fixed a real bug found by launching the app:
  the sidecar was spawned from the wrong working directory.
- Verification run: ./init.sh full run passed; `npm run tauri dev` end to
  end (window + healthy sidecar + migrations).
- Commits: 7de9f13, af10234, 33e8033.

### Session 001

- Date: 2026-10-28
- Goal: Adapt the agent-workflow template to the Stage Finder
  specification (local-first desktop app that automates job/internship
  applications with an LLM and mandatory user confirmation before any
  send).
- Completed:
  - docs/PRODUCT.md rewritten for Stage Finder (product description, hard
    no-auto-send rule, core features, tech requirements, constraints).
  - docs/ARCHITECTURE.md rewritten with the planned architecture (Tauri 2
    minimal Rust core, React renderer, FastAPI sidecar, session-token
    authentication, data flow, storage plan).
  - docs/decisions/: ADR 0001 session-token sidecar, ADR 0002 OpenRouter
    capability-aware integration, ADR 0003 nothing is ever sent
    automatically.
  - feature_list.json: 17 features derived from the spec's Phase 1/2/3
    plan, each with concrete verification steps; all not_started.
  - init.sh: template-only verification while no code exists; full
    verification (uv/pytest/ruff, npm build, cargo check) activates when
    the skeleton lands.
- Verification run: ./init.sh (template-only) passed; feature_list.json is
  valid JSON.
- Evidence captured: init.sh output, session 001 entry in this file.
- Commits: 5ac3239 (adaptation), b1917bc (naming).
- Files or artifacts updated: docs/PRODUCT.md, docs/ARCHITECTURE.md,
  docs/decisions/0001..0003, feature_list.json, init.sh, PROGRESS.md.
- Known risk or unresolved issue: none at the end of the session.
- Next best step: skel-001 (done in session 002).
