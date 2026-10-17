"""Memória local da Friday: factos sobre o utilizador e registo das conversas (SQLite)."""

from __future__ import annotations

import math
import sqlite3
import time
from typing import Literal, Protocol

import sqlite_vec

_DUPLICATE_SIMILARITY = 0.92


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedder:
    """Embeddings multilíngues pequenos, na CPU (o modelo é descarregado na 1.ª utilização)."""

    MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    dim = 384

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(self.MODEL)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class MemoryStore:
    def __init__(self, db_path: str, embedder: Embedder, min_similarity: float = 0.35) -> None:
        self._embedder = embedder
        self._min_similarity = min_similarity
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.enable_load_extension(True)
        sqlite_vec.load(self._db)
        self._db.enable_load_extension(False)
        self._db.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY, text TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_vec USING vec0(
                embedding float[{embedder.dim}] distance_metric=cosine);
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL,
                created_at REAL NOT NULL);
            """
        )

    def _vector(self, text: str) -> bytes:
        return sqlite_vec.serialize_float32(_normalise(self._embedder.embed([text])[0]))

    def _nearest(self, vector: bytes, k: int) -> list[tuple[str, float]]:
        rows = self._db.execute(
            """
            SELECT f.text, v.distance FROM facts_vec v JOIN facts f ON f.id = v.rowid
            WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance
            """,
            (vector, k),
        ).fetchall()
        return [(text, 1.0 - distance) for text, distance in rows]

    def add_fact(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        vector = self._vector(text)
        nearest = self._nearest(vector, 1)
        if nearest and nearest[0][1] >= _DUPLICATE_SIMILARITY:
            return False
        with self._db:
            cur = self._db.execute(
                "INSERT INTO facts (text, created_at) VALUES (?, ?)", (text, time.time())
            )
            self._db.execute(
                "INSERT INTO facts_vec (rowid, embedding) VALUES (?, ?)", (cur.lastrowid, vector)
            )
        return True

    def search(self, query: str, k: int = 3) -> list[str]:
        return [
            text
            for text, sim in self._nearest(self._vector(query), k)
            if sim >= self._min_similarity
        ]

    def log_turn(self, role: Literal["user", "assistant"], text: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO turns (role, text, created_at) VALUES (?, ?, ?)",
                (role, text, time.time()),
            )

    def context_for(self, query: str) -> str:
        return "\n".join(self.search(query))
