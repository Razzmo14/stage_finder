# Session Handoff

## Verified Now

- What is currently working: full skeleton (Tauri 2 core, React/Vite/Tailwind
  renderer, FastAPI sidecar with per-launch session-token auth) and the
  SQLite/SQLModel/Alembic data layer (12 tables, migrations run at sidecar
  startup).
- What verification actually ran: ./init.sh full run (uv sync, npm install,
  ruff, pytest 16 passed, tsc+vite build, cargo check); live smoke tests
  (401 without token / 200 with token; first-run DB creation + migration);
  alembic upgrade/downgrade/re-upgrade on a clean data dir.

## Changed This Session

- Code or behavior added: skel-001 complete (backend/app, src/, src-tauri/,
  README.md, .env.example), db-002 complete (backend/app/db models + engine
  + migrate, backend/alembic.ini + alembic/ + initial revision a1dc86066505,
  tests/test_migrations.py, tests/test_models.py).
- Infrastructure or harness changes: init.sh now runs its full verification
  path (it self-activates once backend/, package.json, src-tauri/ exist);
  Tauri Linux system libraries installed on this machine.

## Broken Or Unverified

- Known defect: none.
- Unverified path: the GUI launched via `npm run tauri dev` has not been
  exercised in this environment (no display); release packaging
  (`tauri build` + PyInstaller sidecar) is feature pkg-016.
- Risk for the next session: the Rust core spawns the sidecar with `uv run`
  from the project directory; this only works in dev checkout. Anything
  that changes the backend entry point (`python -m app`) or the
  STAGE_FINDER_* env var names must update src-tauri/src/lib.rs too.

## Next Best Step

- Highest-priority unfinished feature: llm-003 (OpenRouter client:
  keychain key, live model catalog, capability-aware structured output,
  usage tracking).
- Why it is next: priority order in feature_list.json; it is the
  prerequisite for profile extraction, matching, and letter generation.
- What counts as passing: contract tests with a mocked OpenRouter endpoint
  (native structured-output path AND fallback path with JSON retry),
  API key stored in the OS keychain only and masked in any display, token
  usage and cost recorded in LLMUsage/EventLog.
- What must not change during that step: the session-token middleware, the
  existing models/migrations (extend, do not rewrite), ADR 0003 (no code
  path may send anything automatically).

## Commands

- Startup: ./init.sh
- Verification: ./init.sh (SKIP_CARGO_CHECK=1 to skip the Rust core)
- Focused debug command: cd backend && STAGE_FINDER_PORT=8972
  STAGE_FINDER_SESSION_TOKEN=dev-token uv run python -m app
