# Session Handoff

## Verified Now

- What is currently working: the complete application. Phase 1 and
  Phase 2 features are passing: skeleton (session-token sidecar), DB
  layer, OpenRouter LLM client with capability-aware structured output,
  profile + CV import, France Travail/Adzuna/Jooble search with dedup,
  two-stage matching, letter generation with grounding check, review
  screen with streamed regeneration, Gmail/Graph/SMTP mailers behind a
  single confirmation-gated gateway, application tracking, scheduler,
  direct Anthropic/OpenAI/Ollama providers with budget cap, FR/EN UI.
- What verification actually ran: ./init.sh full run (uv sync, npm
  install, ruff, pytest 118 passed, tsc+vite build, cargo check); the
  real app launched via `npm run tauri dev` (window opened, sidecar
  healthy on 127.0.0.1:46801, migration b2f000000002 applied); the
  PyInstaller sidecar binary boot-verified standalone (401/200 +
  migrations inside the frozen binary). All external endpoints are
  mocked in tests; no test hits the network.

## Changed This Session

- Code or behavior added: features llm-003 through i18n-015 complete;
  pkg-016 and release-017 in progress (details in feature_list.json
  evidence arrays and PROGRESS.md session 003).
- Infrastructure or harness changes: appsetting table (migration
  b2f000000002), settings service module, provider registry, mailer
  account registry, scheduler with stable job IDs, PyInstaller spec +
  build script, CI workflow, updater scaffolding, i18n locales.

## Broken Or Unverified

- Known defect: none known.
- Unverified path: GitHub Actions CI matrix (no git remote in this
  session) — pkg-016 remaining step. Signed installers and update from
  an older version — release-017 remaining steps (need signing
  identities + a published release, documented in docs/RELEASE.md).
- Risk for the next session: release builds spawn the bundled sidecar
  binary named `stage-finder-backend` next to the executable; anything
  that changes backend entry points or the STAGE_FINDER_* env var names
  must update src-tauri/src/lib.rs and pyinstaller.spec together.

## Next Best Step

- Highest-priority unfinished feature: pkg-016 (run the CI matrix), then
  release-017 (signing + auto-update against a published release).
- Why it is next: all local verification for those features is done;
  what remains requires a GitHub remote and signing identities.
- What counts as passing: pkg-016 — CI artifacts (installers) for Linux,
  Windows and macOS; release-017 — signed installers that install and
  run on the three OSes plus a successful update from an older version.
- What must not change during that step: the no-auto-send rule (ADR
  0003), the session-token middleware, existing migrations (extend, do
  not rewrite), the mocked-endpoint test approach.

## Commands

- Startup: ./init.sh
- Verification: ./init.sh (SKIP_CARGO_CHECK=1 to skip the Rust core)
- Run the app: npm run tauri dev
- Build sidecar: ./scripts/build-sidecar.sh [<target-triple>]
- Focused debug command: cd backend && STAGE_FINDER_PORT=8972
  STAGE_FINDER_SESSION_TOKEN=dev-token STAGE_FINDER_DATA_DIR=/tmp/sf
  uv run python -m app
