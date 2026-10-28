"""Microsoft Graph (Outlook) client: OAuth2 (PKCE) + drafts and send.

Same shape as the Gmail client: keychain-only tokens, injectable HTTP
transport for contract tests.
"""

import base64
import hashlib
import secrets as pysecrets
import time

import httpx

from app.core import secrets

AUTH_URL = "https://login.microsoftonline.com/consumer/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/consumer/oauth2/v2.0/token"
GRAPH_API = "https://graph.microsoft.com/v1.0/me"
SCOPES = "offline_access Mail.ReadWrite Mail.Send"

CLIENT_ID_SECRET = "graph_client_id"
ACCESS_TOKEN_SECRET = "graph_access_token"
REFRESH_TOKEN_SECRET = "graph_refresh_token"
TOKEN_EXPIRY_SECRET = "graph_token_expires_at"


class GraphError(Exception):
    pass


def build_graph_message(*, sender: str, to: str, subject: str, body: str) -> dict:
    return {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "from": {"emailAddress": {"address": sender}},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(pysecrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


class GraphClient:
    name = "graph"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=30)

    def start_connect(self, redirect_uri: str) -> tuple[dict, str]:
        client_id = secrets.get_secret(CLIENT_ID_SECRET)
        if not client_id:
            raise GraphError("Graph client_id is not configured (keychain)")
        verifier, challenge = pkce_pair()
        state = pysecrets.token_urlsafe(16)
        from urllib.parse import urlencode

        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        }
        return {"state": state, "code_verifier": verifier, "redirect_uri": redirect_uri}, (
            f"{AUTH_URL}?{urlencode(params)}"
        )

    def complete_connect(self, flow: dict, code: str) -> dict:
        client_id = secrets.get_secret(CLIENT_ID_SECRET)
        with self._client() as client:
            response = client.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": flow["code_verifier"],
                    "redirect_uri": flow["redirect_uri"],
                    "scope": SCOPES,
                },
            )
        if response.status_code != 200:
            raise GraphError(f"Token exchange failed: HTTP {response.status_code}")
        payload = response.json()
        secrets.set_secret(ACCESS_TOKEN_SECRET, payload["access_token"])
        if payload.get("refresh_token"):
            secrets.set_secret(REFRESH_TOKEN_SECRET, payload["refresh_token"])
        secrets.set_secret(
            TOKEN_EXPIRY_SECRET, str(time.time() + float(payload.get("expires_in", 3600)) - 60)
        )
        return {"account": "connected"}

    def connected(self) -> bool:
        return bool(secrets.get_secret(ACCESS_TOKEN_SECRET))

    def _token(self) -> str:
        token = secrets.get_secret(ACCESS_TOKEN_SECRET)
        if not token:
            raise GraphError("Outlook is not connected")
        expiry = secrets.get_secret(TOKEN_EXPIRY_SECRET)
        if expiry and time.time() >= float(expiry):
            self.refresh()
            token = secrets.get_secret(ACCESS_TOKEN_SECRET)
        return token

    def refresh(self) -> None:
        refresh_token = secrets.get_secret(REFRESH_TOKEN_SECRET)
        client_id = secrets.get_secret(CLIENT_ID_SECRET)
        if not refresh_token:
            raise GraphError("Outlook is not connected")
        with self._client() as client:
            response = client.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": SCOPES,
                },
            )
        if response.status_code != 200:
            raise GraphError(f"Token refresh failed: HTTP {response.status_code}")
        payload = response.json()
        secrets.set_secret(ACCESS_TOKEN_SECRET, payload["access_token"])
        secrets.set_secret(
            TOKEN_EXPIRY_SECRET, str(time.time() + float(payload.get("expires_in", 3600)) - 60)
        )

    def create_draft(self, mime: bytes) -> dict:
        # Graph drafts use the JSON message shape; parse the MIME we build.
        import email
        from email import policy

        parsed = email.message_from_bytes(mime, policy=policy.default)
        body = parsed.get_body(preferencelist=("plain",)).get_content()
        payload = {
            "subject": str(parsed["Subject"]),
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in str(parsed["To"]).split(",")
            ],
        }
        with self._client() as client:
            response = client.post(
                f"{GRAPH_API}/messages",
                headers={"Authorization": f"Bearer {self._token()}"},
                json=payload,
            )
        if response.status_code not in (200, 201):
            raise GraphError(f"Draft creation failed: HTTP {response.status_code}")
        return response.json()

    def send(self, mime: bytes) -> dict:
        import email
        from email import policy

        parsed = email.message_from_bytes(mime, policy=policy.default)
        message = build_graph_message(
            sender=str(parsed["From"]),
            to=str(parsed["To"]),
            subject=str(parsed["Subject"]),
            body=parsed.get_body(preferencelist=("plain",)).get_content(),
        )
        with self._client() as client:
            response = client.post(
                f"{GRAPH_API}/sendMail",
                headers={"Authorization": f"Bearer {self._token()}"},
                json=message,
            )
        if response.status_code not in (200, 202):
            raise GraphError(f"Send failed: HTTP {response.status_code}")
        return {"id": "graph-send"}
