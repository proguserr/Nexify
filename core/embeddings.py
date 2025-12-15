# core/embeddings.py

"""
Embedding helpers for knowledge base chunks.

PR10 version:
- Uses a deterministic dummy embedding so we can wire plumbing
  and pgvector without needing a real external model yet.
- Later you can swap get_embedding() to call OpenAI / other provider.
"""

from __future__ import annotations

import hashlib
import random
from typing import List

# Must match your pgvector column dim
EMBEDDING_DIM = 1536


def _rng_for_text(text: str) -> random.Random:
    """
    Build a deterministic RNG seeded from the text.
    That way the same text -> same "embedding" every time.
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # Use the digest bytes as an int seed
    seed = int.from_bytes(h, byteorder="big")
    return random.Random(seed)


def get_embedding(text: str) -> List[float]:
    """
    Return a deterministic list[float] of length EMBEDDING_DIM.

    This is a STUB implementation for PR10:
    - Good enough to test pgvector + Celery + plumbing.
    - Replace later with a real provider (OpenAI, etc.).
    """
    text = (text or "").strip()

    if not text:
        # Degenerate, but valid embedding
        return [0.0] * EMBEDDING_DIM

    rng = _rng_for_text(text)
    # Uniform in [-1.0, 1.0] just to have "nice" numbers
    return [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIM)]


def get_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Simple batch helper; for now just loops get_embedding().
    Later you can optimize to call a batch embedding API.
    """
    return [get_embedding(t) for t in texts]
