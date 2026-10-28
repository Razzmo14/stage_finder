# ADR 0001: Localhost sidecar with per-launch session token

Date: 2026-10-28
Status: Accepted (planned)

## Context

Stage Finder needs a local backend (Python/FastAPI) for business logic and a
frontend (React inside Tauri). Anything listening on a local port can be
reached by other processes on the machine, and a desktop app cannot rely on
the browser same-origin model alone.

## Decision

- Tauri spawns the FastAPI sidecar on a random free port bound to 127.0.0.1
  only.
- Tauri generates a cryptographically random session token at launch and
  passes it to both the sidecar (environment) and the frontend (invoke).
- Every request must carry `Authorization: Bearer <token>`; the sidecar
  rejects everything else with 401, including `/health`.
- The sidecar is health-checked and restarted on crash, and killed when the
  app closes.

## Consequences

- Other local processes cannot use the backend without the in-memory token.
- The token never touches disk or logs, so it dies with the app.
- Contract tests can spawn the app programmatically with a known token.
