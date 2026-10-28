"""Gmail client: OAuth2 (PKCE) connect, draft creation, send.

All HTTP calls go through an injectable transport; contract tests run
against mocked endpoints. Tokens live in the OS keychain only.
"""

import base64
import hashlib
import json
import secrets as pysecrets
import time
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.core import secrets

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = "https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.send"

CLIENT_ID_SECRET = "gmail_client_id"
CLIENT_SECRET_SECRET = "gmail_client_secret"  # Google "Desktop" apps use it with PKCE
ACCESS_TOKEN_SECRET = "gmail_access_token"
REFRESH_TOKEN_SECRET = "gmail_refresh_token"
TOKEN_EXPIRY_SECRET = "gmail_token_expires_at"


class GmailError(Exception):
    pass


@dataclass
class OAuthState:
    """Per-connect PKCE state (in memory only)."""

    state: str
    code_verifier: str
    code_challenge: str
    redirect_uri: str

    def authorize_url(self, client_id: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "state": self.state,
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{AUTH_URL}?{urlencode(params)}"


def new_oauth_state(redirect_uri: str) -> OAuthState:
    verifier = base64.urlsafe_b64encode(pysecrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return OAuthState(
        state=pysecrets.token_urlsafe(16),
        code_verifier=verifier,
        code_challenge=challenge,
        redirect_uri=redirect_uri,
    )


def build_mime(
    *, sender: str, to: str, subject: str, body: str, attachment_texts: dict[str, str] | None = None
) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    for filename, text in (attachment_texts or {}).items():
        message.add_attachment(text.encode(), maintype="text", subtype="plain", filename=filename)
    return message.as_bytes()


def encode_raw(mime: bytes) -> str:
    return base64.urlsafe_b64encode(mime).decode()


class GmailClient:
    """Gmail REST client with keychain token storage."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=30)

    # --- OAuth ---------------------------------------------------------

    def start_connect(self, redirect_uri: str) -> tuple[OAuthState, str]:
        client_id = secrets.get_secret(CLIENT_ID_SECRET)
        if not client_id:
            raise GmailError("Gmail client_id is not configured (keychain)")
        state = new_oauth_state(redirect_uri)
        return state, state.authorize_url(client_id)

    def complete_connect(self, state: OAuthState, code: str) -> dict:
        client_id = secrets.get_secret(CLIENT_ID_SECRET)
        client_secret = secrets.get_secret(CLIENT_SECRET_SECRET)
        if not client_id:
            raise GmailError("Gmail client_id is not configured (keychain)")
        with self._client() as client:
            response = client.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret or "",
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": state.code_verifier,
                    "redirect_uri": state.redirect_uri,
                },
            )
        if response.status_code != 200:
            raise GmailError(f"Token exchange failed: HTTP {response.status_code}")
        payload = response.json()
        _store_tokens(payload)
        return {"email_address": payload.get("email_address", "connected")}

    def refresh_access_token(self) -> None:
        refresh_token = secrets.get_secret(REFRESH_TOKEN_SECRET)
        client_id = secrets.get_secret(CLIENT_ID_SECRET)
        client_secret = secrets.get_secret(CLIENT_SECRET_SECRET)
        if not refresh_token or not client_id:
            raise GmailError("Gmail is not connected")
        with self._client() as client:
            response = client.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret or "",
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
        if response.status_code != 200:
            raise GmailError(f"Token refresh failed: HTTP {response.status_code}")
        _store_tokens(response.json())

    def access_token(self) -> str:
        token = secrets.get_secret(ACCESS_TOKEN_SECRET)
        expiry_raw = secrets.get_secret(TOKEN_EXPIRY_SECRET)
        if not token:
            raise GmailError("Gmail is not connected")
        if expiry_raw and time.time() >= float(expiry_raw):
            self.refresh_access_token()
            token = secrets.get_secret(ACCESS_TOKEN_SECRET)
        return token  # type: ignore[return-value]

    def connected(self) -> bool:
        return bool(secrets.get_secret(ACCESS_TOKEN_SECRET))

    # --- Gmail API -----------------------------------------------------

    def create_draft(self, mime: bytes) -> dict:
        token = self.access_token()
        with self._client() as client:
            response = client.post(
                f"{GMAIL_API}/drafts",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": {"raw": encode_raw(mime)}},
            )
        if response.status_code not in (200, 201):
            raise GmailError(f"Draft creation failed: HTTP {response.status_code}")
        return response.json()

    def send(self, mime: bytes) -> dict:
        token = self.access_token()
        with self._client() as client:
            response = client.post(
                f"{GMAIL_API}/messages/send",
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": encode_raw(mime)},
            )
        if response.status_code not in (200, 201):
            raise GmailError(f"Send failed: HTTP {response.status_code}")
        return response.json()


def _store_tokens(payload: dict) -> None:
    if "access_token" in payload:
        secrets.set_secret(ACCESS_TOKEN_SECRET, payload["access_token"])
    if "refresh_token" in payload:
        secrets.set_secret(REFRESH_TOKEN_SECRET, payload["refresh_token"])
    expires_in = payload.get("expires_in", 3600)
    secrets.set_secret(TOKEN_EXPIRY_SECRET, json.dumps(time.time() + float(expires_in) - 60))
