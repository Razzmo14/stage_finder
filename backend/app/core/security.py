"""Session-token authentication middleware (ADR 0001).

Every request, including /health, must carry a valid Bearer token matching
the per-launch token passed by the Tauri core. Anything else is rejected
with 401 before it reaches a route.
"""

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class SessionTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        expected = request.app.state.session_token
        authorization = request.headers.get("Authorization", "")
        scheme, _, provided = authorization.partition(" ")
        if (
            not expected
            or scheme.lower() != "bearer"
            or not provided
            or not hmac.compare_digest(expected, provided)
        ):
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        return await call_next(request)
