# Stage Finder

Local-first, cross-platform desktop application that automates job and
internship applications, assisted by an LLM, while the user always keeps the
final say before anything is sent.

**Hard rule:** nothing is ever sent automatically. Every send requires an
explicit user action on a final confirmation dialog, per application. See
`docs/decisions/0003-no-auto-send.md`.

Status: Phase 1 in progress. The plan of record is `feature_list.json`;
the current verified state is in `PROGRESS.md`.

## Stack

- **Desktop shell:** Tauri 2 (`src-tauri/`) -- minimal Rust core: window
  lifecycle, sidecar supervision, per-launch session token, two commands.
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS (`src/`).
- **Backend:** Python 3.12 + FastAPI sidecar (`backend/`), started by the
  Tauri core on a random 127.0.0.1 port; uv for dependencies.
- **Database:** SQLite via SQLModel (arriving with feature `db-002`).

Every backend request must carry `Authorization: Bearer <session-token>`;
the token is generated per launch, held in memory only, and never written
to disk or logs (ADR 0001).

## Prerequisites

- Node.js >= 18 and npm
- Rust (stable) and cargo: https://rustup.rs
- Python 3.12 and uv: https://docs.astral.sh/uv/
- Linux only: Tauri system libraries

    ```sh
    sudo apt-get install -y \
      libwebkit2gtk-4.1-dev build-essential curl wget file \
      libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
    ```

  (macOS: Xcode Command Line Tools; Windows: WebView2, installed by default
  on Windows 10/11.)

## Setup

```sh
git clone <repo> && cd stage_finder
uv sync --project backend   # Python backend environment
npm install                 # Frontend dependencies
```

## Development

```sh
npm run tauri dev           # Desktop app: builds, spawns the sidecar, opens the window
```

The status bar at the bottom of the app window shows the sidecar health,
fetched from the authenticated `/health` endpoint.

To run the backend alone (e.g. for API work):

```sh
cd backend
STAGE_FINDER_PORT=8000 STAGE_FINDER_SESSION_TOKEN=dev-token uv run python -m app
# In another terminal:
curl -H "Authorization: Bearer dev-token" http://127.0.0.1:8000/health
```

The frontend alone (plain browser, no Tauri shell):

```sh
npm run dev                 # http://localhost:1420
```

## Verification

The standard startup and verification path is:

```sh
./init.sh
```

It syncs dependencies and runs: `ruff check`, `pytest` (backend),
`tsc && vite build` (frontend), and `cargo check` (Rust core).
Set `SKIP_CARGO_CHECK=1` to skip the Rust core, `RUN_START_COMMAND=1` to
launch the app at the end.

## Build (release)

```sh
./scripts/build-sidecar.sh          # PyInstaller sidecar -> src-tauri/binaries/<name>-<triple>
npm run tauri build                 # bundles the sidecar as externalBin
```

- In dev (`npm run tauri dev`) the core spawns the backend via `uv run`.
- In release builds it spawns the bundled PyInstaller sidecar installed
  next to the main executable (one binary per OS/architecture, declared
  via `externalBin` in `src-tauri/tauri.conf.json`).
- CI (`.github/workflows/build.yml`) builds installers for Linux, Windows
  and macOS on push.

## Layout

```
backend/          FastAPI sidecar (app/api, app/core, app/db, app/services)
src/               React renderer
src-tauri/         Tauri core (minimal Rust)
docs/              PRODUCT.md, ARCHITECTURE.md, decisions/ (ADRs)
feature_list.json  Source of truth for feature state
PROGRESS.md        Session log and current verified status
init.sh            Standard startup + verification path
```

## Secrets and privacy

- No secrets in `.env`, source control, or the database: OS keychain only.
- All data stays local except what is sent to the chosen LLM gateway and
  the email provider.
- GDPR by design: consent, data export, full deletion, privacy-preserving
  OpenRouter routing by default.
