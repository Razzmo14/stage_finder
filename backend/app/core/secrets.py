"""Secret storage: OS keychain only (ADR 0002).

No secret is ever written to the database, a file, or a log. The backend of
this module is swappable so tests can run with an in-memory store.
"""

from typing import Protocol

SERVICE_NAME = "stage-finder"


class SecretBackend(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...


class KeyringBackend:
    """Default backend: the OS keychain via the keyring package."""

    def get(self, name: str) -> str | None:
        import keyring

        return keyring.get_password(SERVICE_NAME, name)

    def set(self, name: str, value: str) -> None:
        import keyring

        keyring.set_password(SERVICE_NAME, name, value)

    def delete(self, name: str) -> None:
        import keyring

        keyring.delete_password(SERVICE_NAME, name)


class MemoryBackend:
    """In-memory backend for tests."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.store.get(name)

    def set(self, name: str, value: str) -> None:
        self.store[name] = value

    def delete(self, name: str) -> None:
        self.store.pop(name, None)


_backend: SecretBackend = KeyringBackend()


def use_backend(backend: SecretBackend) -> None:
    """Swap the backend (used by tests and tooling)."""
    global _backend
    _backend = backend


def get_secret(name: str) -> str | None:
    return _backend.get(name)


def set_secret(name: str, value: str) -> None:
    _backend.set(name, value)


def delete_secret(name: str) -> None:
    _backend.delete(name)


def mask(value: str | None) -> str | None:
    """Mask a secret for display: first 4 + last 4 characters."""
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
