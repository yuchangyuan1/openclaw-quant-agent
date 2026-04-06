from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections import Counter


_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")
_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return _SPACE_RE.sub(" ", text or "").strip()


def sha256_hexdigest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def stable_uuid(text: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, text))


def tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []
    for piece in _TOKEN_RE.findall(text or ""):
        if re.fullmatch(r"[\u4e00-\u9fff]+", piece):
            tokens.extend(piece)
            tokens.extend(piece[i : i + 2] for i in range(len(piece) - 1))
        else:
            tokens.append(piece.lower())
    return [token for token in tokens if token]


def hashed_embedding(text: str, dim: int) -> list[float]:
    vector = [0.0] * dim
    for token, freq in Counter(tokenize_text(text)).items():
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = -1.0 if digest[4] % 2 else 1.0
        vector[index] += sign * float(freq)

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def chunk_text(text: str, chunk_size: int = 480, overlap: int = 80) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunks.append(normalized[start:end])
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


def build_snippet(text: str, query: str, max_chars: int = 180) -> str:
    normalized = normalize_text(text)
    if len(normalized) <= max_chars:
        return normalized

    lowered = normalized.lower()
    for token in tokenize_text(query):
        if len(token) < 2:
            continue
        idx = lowered.find(token.lower())
        if idx >= 0:
            start = max(0, idx - max_chars // 3)
            end = min(len(normalized), start + max_chars)
            return normalized[start:end]
    return normalized[:max_chars]
