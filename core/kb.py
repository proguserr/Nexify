# core/kb.py
from __future__ import annotations

import os
import logging
from typing import List

from pgvector.django import CosineDistance

from core.models import DocumentChunk

import numpy as np

logger = logging.getLogger(__name__)

# =====================================================
# Dimensions: DB vs model
# =====================================================

# DB / pgvector dimension (this is what your migrations & column use)
EMBED_DIM = 1536

# Local sentence-transformers model dimension (MiniLM)
MODEL_DIM = 384

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_MODEL_NAME)

# IMPORTANT: force CPU – avoids MPS + Celery crashes on macOS.
_DEVICE = "cpu"

# Lazy-loaded; None means "not attempted yet", _EMBEDDER_FAILED means give up.
_embedder: object | None = None
_embedder_failed: bool = False


def _load_sentence_transformer():
    """
    Import and construct SentenceTransformer only when embeddings are needed.
    Returns None if the package is missing or the model cannot be loaded.
    """
    global _embedder, _embedder_failed
    if _embedder_failed:
        return None
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        logger.warning(
            "sentence_transformers is not installed; KB vector embeddings disabled (%s)",
            exc,
        )
        _embedder_failed = True
        return None
    try:
        logger.info(
            "Using SentenceTransformer(%s) on device=%s for KB embeddings "
            "(model_dim=%s, db_dim=%s).",
            EMBEDDING_MODEL_NAME,
            _DEVICE,
            MODEL_DIM,
            EMBED_DIM,
        )
        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device=_DEVICE)
        return _embedder
    except Exception as exc:
        logger.warning(
            "Could not load SentenceTransformer; KB vector embeddings disabled (%s)",
            exc,
        )
        _embedder_failed = True
        return None

# =====================================================
# Text normalization + chunking
# =====================================================


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def chunk_text(
    text: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[tuple[int, int, str]]:
    """
    Sliding-window chunking with character indices.
    Returns a list of (char_start, char_end, chunk_str).
    """
    text = text or ""
    n = len(text)
    if n == 0:
        return []

    if overlap >= chunk_size:
        overlap = max(0, chunk_size - 1)

    step = max(1, chunk_size - overlap)
    out: list[tuple[int, int, str]] = []

    i = 0
    while i < n:
        start = i
        end = min(n, i + chunk_size)
        chunk_str = text[start:end]
        if chunk_str.strip():  # skip pure-whitespace chunks
            out.append((start, end, chunk_str))
        if end >= n:
            break
        i += step

    return out


# =====================================================
# Embeddings (local model) – pad to DB dim
# =====================================================


def _pad_to_db_dim(vec: np.ndarray) -> np.ndarray:
    """
    Take a MODEL_DIM vector and pad/truncate to EMBED_DIM for pgvector.
    """
    if vec.shape[0] == EMBED_DIM:
        return vec
    if vec.shape[0] > EMBED_DIM:
        return vec[:EMBED_DIM]

    pad_len = EMBED_DIM - vec.shape[0]
    if pad_len > 0:
        vec = np.concatenate([vec, np.zeros(pad_len, dtype=vec.dtype)])
    return vec


def embed_texts(texts: List[str]) -> list[list[float]]:
    """
    Embed a list of strings using the shared SentenceTransformer model.

    Returns a list of EMBED_DIM-length vectors as Python lists,
    compatible with your pgvector(1536) column.

    If ``sentence_transformers`` is unavailable or encoding fails, returns [].
    """
    if not texts:
        return []

    embedder = _load_sentence_transformer()
    if embedder is None:
        return []

    try:
        embeddings = embedder.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
    except Exception as exc:
        logger.warning("SentenceTransformer encode failed: %s", exc, exc_info=True)
        return []

    if embeddings.ndim == 1:  # single text
        embeddings = embeddings.reshape(1, -1)

    if embeddings.shape[1] != MODEL_DIM:
        logger.warning(
            "SentenceTransformer produced dim=%s but MODEL_DIM=%s",
            embeddings.shape[1],
            MODEL_DIM,
        )

    padded = np.vstack([_pad_to_db_dim(v) for v in embeddings])
    return padded.tolist()


# =====================================================
# Vector search
# =====================================================


def search_kb_chunks_for_query(
    org_id: int,
    query: str,
    k: int = 5,
) -> list[dict]:
    """
    Vector similarity search over DocumentChunk.embedding for a given organization.

    Returns:
      [
        {
          "document_id": ...,
          "document_title": ...,
          "chunk_id": ...,
          "chunk_index": ...,
          "text": ...,
          "score": <cosine_distance>,
        },
        ...
      ]
    """
    query = normalize_text(query)
    if not query:
        return []

    # Embed query once → already padded to EMBED_DIM
    query_vecs = embed_texts([query])
    if not query_vecs:
        return []
    query_vec = query_vecs[0]

    qs = (
        DocumentChunk.objects.filter(organization_id=org_id, embedding__isnull=False)
        .select_related("document")
        .annotate(distance=CosineDistance("embedding", query_vec))
        .order_by("distance")[:k]
    )

    results: list[dict] = []
    for c in qs:
        dist = getattr(c, "distance", None)
        results.append(
            {
                "document_id": c.document_id,
                "document_title": c.document.title if c.document_id else None,
                "chunk_id": c.id,
                "chunk_index": c.chunk_index,
                "text": c.text,
                "score": float(dist) if dist is not None else None,
            }
        )

    return results
