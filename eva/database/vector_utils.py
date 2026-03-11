"""Vector helpers for semantic index storage and retrieval."""

from __future__ import annotations

import numpy as np


def vector_to_blob(vector: list[float]) -> bytes:
    """Serialize a float vector as compact float32 bytes for SQLite BLOB storage."""
    return np.asarray(vector, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes) -> list[float]:
    """Deserialize float32 bytes from SQLite BLOB into a Python float list."""
    return np.frombuffer(blob, dtype=np.float32).tolist()


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Return cosine similarity in [-1, 1], or -1 when vectors are invalid."""
    arr_a = np.asarray(vec_a, dtype=np.float32)
    arr_b = np.asarray(vec_b, dtype=np.float32)

    if arr_a.shape != arr_b.shape:
        return -1.0

    norm_a = float(np.linalg.norm(arr_a))
    norm_b = float(np.linalg.norm(arr_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return -1.0

    dot = float(np.dot(arr_a, arr_b))
    return dot / (norm_a * norm_b)
