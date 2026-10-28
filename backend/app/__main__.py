"""Entry point: `python -m app` starts the sidecar with uvicorn.

The host must remain 127.0.0.1; the port and session token come from the
environment provided by the Tauri core.
"""

import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
