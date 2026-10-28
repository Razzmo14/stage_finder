"""Pluggable embeddings, independent from the chat model (ADR 0002).

The default provider is a local, deterministic hashing embedder (no model
download, works offline). An API-based provider (OpenAI-compatible
/embeddings) is available for users who prefer it. The model name is stored
with every vector so changing the provider never invalidates silently.
"""

import hashlib
import math
import re
import struct
from typing import Protocol

import httpx

from app.core import secrets
from app.llm.openrouter import API_KEY_SECRET

BASE_URL = "https://openrouter.ai/api/v1"


class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]


class HashingEmbedder:
    """Deterministic local embeddings: hashed bag of words + bigrams."""

    name = "local-hashing-v1"
    dim = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            weight = int.from_bytes(digest[4:], "little") % 8 + 1
            vector[bucket] += weight
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class ApiEmbedder:
    """OpenAI-compatible /embeddings endpoint (e.g. via OpenRouter)."""

    def __init__(self, model: str, transport: httpx.BaseTransport | None = None) -> None:
        self.model = model
        self.name = f"api:{model}"
        self._transport = transport
        self.dim = 1536  # overwritten by the first response

    def embed(self, texts: list[str]) -> list[list[float]]:
        api_key = secrets.get_secret(API_KEY_SECRET)
        if not api_key:
            raise RuntimeError("OpenRouter API key is not configured")
        with httpx.Client(transport=self._transport, timeout=60) as client:
            response = client.post(
                f"{BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
        vectors = [item["embedding"] for item in payload["data"]]
        if vectors:
            self.dim = len(vectors[0])
        return vectors


# --- serialization -----------------------------------------------------------


def encode_vector(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def decode_vector(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
