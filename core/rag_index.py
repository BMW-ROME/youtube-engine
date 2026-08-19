"""
core/rag_index.py -- Hybrid transcript RAG over produced videos.

Every video's script (hook + per-scene narration + outro) is already stored in
content_db metadata_json["script"], so this module builds a tiny local
searchable library from it, without any network call at index time:

  - Retrieval layer 1: SQLite FTS5 full-text keyword search (zero deps, works
    fully offline on every run).
  - Retrieval layer 2: semantic vector ranking via an Ollama-compatible
    /api/embeddings endpoint (settings.embeddings_base_url). If the embed
    model is missing or the endpoint is down, results degrade gracefully to
    FTS-only with "vector": False instead of raising.

Code sits in its own SQLite store (settings.rag_db_file, default output/rag.db)
so content.db stays untouched. All public functions follow the repo resilience
contract: never raise to the caller, log and degrade.

Public API:
    init_db() -> None
    index_video(video_id) -> dict
    index_all(channel=None, rebuild=False, reset=False) -> dict
    unindex(video_id) -> bool
    search(query, top_k=5, channel=None) -> list[dict]
    ask(question, sources=3) -> dict
    status() -> dict
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

EMBED_TIMEOUT_SECONDS = 60

# Chunk kinds mirror the Script schema produced by script_writer.generate_script.
CHUNK_HOOK = "hook"
CHUNK_SCENE = "scene"
CHUNK_OUTRO = "outro"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    video_id   INTEGER PRIMARY KEY,
    channel    TEXT,
    topic      TEXT,
    status     TEXT,
    chunk_count   INTEGER DEFAULT 0,
    vector_count  INTEGER DEFAULT 0,
    indexed_at    TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id    INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    source      TEXT,
    scene_index INTEGER,
    content     TEXT NOT NULL,
    vector_json TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content, tokenize='unicode61');
"""


class EmbeddingError(Exception):
    """Raised when the embed endpoint is unreachable / returns garbage."""


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    from config.settings import settings
    conn = sqlite3.connect(str(settings.rag_db_file))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Embedding (optional, degradable)
# ---------------------------------------------------------------------------

class OllamaEmbedder:
    """Minimal client for an Ollama-compatible /api/embeddings endpoint."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        from config.settings import settings
        self.base_url = (base_url or settings.embeddings_base_url).rstrip("/")
        self.model = model or settings.rag_embedding_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            import requests
        except ImportError as exc:
            raise EmbeddingError(f"requests not installed: {exc}")

        out: list[list[float]] = []
        for text in texts:
            try:
                resp = requests.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=EMBED_TIMEOUT_SECONDS,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:  # noqa: BLE001 - degrade, never kill a search
                raise EmbeddingError(f"embed request failed: {exc}")
            if "embeddings" in data and data["embeddings"]:
                vec = data["embeddings"][0]
            elif "embedding" in data:
                vec = data["embedding"]
            else:
                raise EmbeddingError("embed response missing 'embedding(s)' key")
            out.append(list(vec))
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunks_from_script(script: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    hook = (script.get("hook") or "").strip()
    if hook:
        chunks.append({"content": hook, "source": CHUNK_HOOK, "scene_index": None})
    for index, scene in enumerate(script.get("scenes") or []):
        narration = (scene.get("narration") or "").strip()
        if narration:
            chunks.append({
                "content": narration,
                "source": CHUNK_SCENE,
                "scene_index": index,
            })
    outro = (script.get("outro") or "").strip()
    if outro:
        chunks.append({"content": outro, "source": CHUNK_OUTRO, "scene_index": None})
    return chunks


def _transcript(video_id: int) -> Optional[dict[str, Any]]:
    """Return {topic, channel, status, chunks} for a video, or None."""
    from core import content_db
    record = content_db.get_video(video_id)
    if record is None:
        return None
    script = (record.metadata or {}).get("script")
    return {
        "topic": record.topic,
        "channel": record.channel,
        "status": record.status,
        "chunks": _chunks_from_script(script or {}),
    }


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def _sync_fts(conn: sqlite3.Connection, chunk_id: int, content: str) -> None:
    conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
    conn.execute(
        "INSERT INTO chunks_fts (rowid, content) VALUES (?, ?)", (chunk_id, content)
    )


def index_video(video_id: int) -> dict[str, Any]:
    """Index (or re-index) one video's transcript. Never raises."""
    init_db()
    from core import content_db
    if content_db.get_video(video_id) is None:
        logger.warning("rag_index: video %s not found in content_db", video_id)
        return {"video_id": video_id, "status": "skipped", "reason": "video not found"}
    transcript = _transcript(video_id)
    if not transcript or not transcript["chunks"]:
        logger.warning("rag_index: video %s has no script to index", video_id)
        return {"video_id": video_id, "status": "skipped", "reason": "no script"}

    embedder = OllamaEmbedder()
    vectors: list[Optional[list[float]]] = [None] * len(transcript["chunks"])
    vector_count = 0
    vector_error: Optional[str] = None
    try:
        vectors = embedder.embed([c["content"] for c in transcript["chunks"]])  # type: ignore[assignment]
        vector_count = len(vectors)
    except Exception as exc:  # noqa: BLE001 - degrade to FTS-only
        vector_error = str(exc)
        logger.warning(
            "rag_index: embedding unavailable for video %s (%s) - FTS-only index",
            video_id, exc,
        )

    with _conn() as conn:
        conn.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
        conn.execute(
            "DELETE FROM chunks_fts WHERE rowid IN "
            "(SELECT id FROM chunks WHERE video_id = ?)",
            (video_id,),
        )
        conn.execute("DELETE FROM documents WHERE video_id = ?", (video_id,))
        for index, chunk in enumerate(transcript["chunks"]):
            cur = conn.execute(
                "INSERT INTO chunks (video_id, chunk_index, source, scene_index, "
                "content, vector_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    video_id,
                    index,
                    chunk["source"],
                    chunk["scene_index"],
                    chunk["content"],
                    json.dumps(vectors[index]) if vectors[index] is not None else None,
                ),
            )
            _sync_fts(conn, cur.lastrowid, chunk["content"])
        conn.execute(
            "INSERT INTO documents (video_id, channel, topic, status, chunk_count, "
            "vector_count, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                video_id,
                transcript["channel"],
                transcript["topic"],
                transcript["status"],
                len(transcript["chunks"]),
                vector_count,
                _now(),
            ),
        )
    logger.info(
        "rag_index: indexed video %s (%d chunks, %d vectors)%s",
        video_id, len(transcript["chunks"]), vector_count,
        "" if not vector_error else f" [{vector_error}]",
    )
    return {
        "video_id": video_id,
        "status": "indexed",
        "chunks": len(transcript["chunks"]),
        "vectors": vector_count,
    }


def index_all(
    channel: Optional[str] = None,
    rebuild: bool = False,
    reset: bool = False,
) -> dict[str, Any]:
    """Index every video that has a script. reset wipes the store first;
    rebuild re-indexes already-indexed videos too."""
    init_db()
    from core import content_db
    content_db.init_db()

    if reset or rebuild:
        with _conn() as conn:
            conn.execute("DELETE FROM documents")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM chunks_fts")
        logger.info("rag_index: store wiped (%s)", "reset" if reset else "rebuild")

    indexed: list[int] = []
    skipped = 0
    rows = content_db.list_videos(channel=channel, limit=10000)
    for record in rows:
        with _conn() as conn:
            already = conn.execute(
                "SELECT 1 FROM documents WHERE video_id = ?", (record.id,)
            ).fetchone()
        if already and not rebuild:
            continue
        result = index_video(record.id)
        if result.get("status") == "indexed":
            indexed.append(record.id)
        else:
            skipped += 1
    return {"total_videos": len(rows), "indexed": len(indexed), "skipped": skipped}


def unindex(video_id: int) -> bool:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM chunks_fts WHERE rowid IN "
            "(SELECT id FROM chunks WHERE video_id = ?)",
            (video_id,),
        )
        conn.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
        gone = conn.execute("DELETE FROM documents WHERE video_id = ?", (video_id,))
        return gone.rowcount > 0


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _fts_query_terms(query: str) -> str:
    words = re.findall(r"\w+", query.lower())[:12]
    if not words:
        return ""
    return " AND ".join(f'"{w}"' for w in words)


def _load_all_chunks(channel: Optional[str] = None) -> list[sqlite3.Row]:
    sql = (
        "SELECT c.id, c.video_id, c.chunk_index, c.source, c.scene_index, "
        "c.content, c.vector_json, d.channel, d.topic "
        "FROM chunks c JOIN documents d ON d.video_id = c.video_id"
    )
    params: list[Any] = []
    if channel:
        sql += " WHERE d.channel = ?"
        params.append(channel)
    with _conn() as conn:
        return conn.execute(sql, params).fetchall()


def search(
    query: str,
    top_k: int = 5,
    channel: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Hybrid search: FTS5 keyword matches merged with optional vector
    cosine ranking. Returns ranked chunks, never raises."""
    init_db()
    query = (query or "").strip()
    if not query or top_k <= 0:
        return []

    fts_query = _fts_query_terms(query)
    fts_scores: dict[int, float] = {}
    if fts_query:
        sql = (
            "SELECT c.id, bm25(chunks_fts) AS rank FROM chunks_fts "
            "JOIN chunks c ON c.id = chunks_fts.rowid "
            "JOIN documents d ON d.video_id = c.video_id "
            "WHERE chunks_fts MATCH ?"
        )
        params: list[Any] = [fts_query, top_k * 4]
        if channel:
            sql += " AND d.channel = ?"
            params.insert(1, channel)
        sql += " ORDER BY rank LIMIT ?"
        try:
            with _conn() as conn:
                fts_rank = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("rag_index: FTS query failed (%s) - vector only", exc)
            fts_rank = []
        if fts_rank:
            ranks = [r["rank"] for r in fts_rank]
            rmin, rmax = min(ranks), max(ranks)
            span = (rmax - rmin) or 1.0
            for row in fts_rank:
                fts_scores[row["id"]] = 1.0 - ((row["rank"] - rmin) / span)

    # Vector layer: rank over the whole (channel-filtered) corpus.
    vector_available = False
    chunk_rows = _load_all_chunks(channel)
    if chunk_rows:
        try:
            query_vector = OllamaEmbedder().embed([query])[0]
            for row in chunk_rows:
                if not row["vector_json"]:
                    continue
                vector = json.loads(row["vector_json"])
                if vector:
                    cos = _cosine(query_vector, vector)
                    fts_scores[row["id"]] = max(fts_scores.get(row["id"], 0.0), cos)
                    vector_available = True
        except Exception as exc:  # noqa: BLE001 - degrade to FTS-only
            logger.warning("rag_index: vector ranking unavailable (%s) - FTS-only", exc)

    if not fts_scores:
        return []

    id_to_row = {row["id"]: row for row in chunk_rows}
    scored: list[dict[str, Any]] = []
    for chunk_id, score in fts_scores.items():
        row = id_to_row.get(chunk_id)
        if not row:
            continue
        scored.append({
            "video_id": row["video_id"],
            "chunk_index": row["chunk_index"],
            "source": row["source"],
            "scene_index": row["scene_index"],
            "content": row["content"],
            "channel": row["channel"],
            "topic": row["topic"],
            "score": round(score, 4),
            "vector": vector_available,
        })
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def ask(question: str, sources: int = 3) -> dict[str, Any]:
    """Retrieve the best-matching transcript chunks and answer a question with
    the configured chat LLM (strict JSON). Degrades to source-only answer if
    the LLM is unavailable."""
    init_db()
    hits = search(question, top_k=sources)
    if not hits:
        return {"question": question, "answer": "No matching content found.", "sources": []}
    answer = ""
    llm_failed = False
    try:
        from core.script_writer import OpenAIChatClient
        from config.settings import settings
        context = "\n---\n".join(
            f"[video {h['video_id']}, {h.get('topic') or h.get('channel')}] {h['content']}"
            for h in hits
        )
        system = (
            "You help a creator answer questions from their own video library. "
            "Answer ONLY from the provided transcript snippets. "
            'Reply with strict JSON: {"answer": "<your answer>"}.'
        )
        raw = OpenAIChatClient().create_chat_completion(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"QUESTION: {question}\n\n"
                    f"TRANSCRIPTS:\n{context}\n\nReturn the JSON answer.",
                },
            ],
            response_format={"type": "json_object"},
        )
        parsed = json.loads(raw)
        answer = str(parsed.get("answer") or "").strip()
    except Exception as exc:  # noqa: BLE001 - LLM optional, degrade gracefully
        llm_failed = True
        logger.warning("rag_index: ask LLM failed (%s) - returning sources only", exc)
    if not answer:
        answer = f"Found {len(hits)} matching transcript chunks."
        if llm_failed:
            answer = f"{answer} (LLM unavailable - sources below.)"

    source_list: list[dict[str, Any]] = []
    try:
        from core import content_db
    except Exception:  # noqa: BLE001
        content_db = None
    for hit in hits:
        url = ""
        if content_db is not None:
            try:
                record = content_db.get_video(hit["video_id"])
                if record:
                    url = record.youtube_url or ""
            except Exception:  # noqa: BLE001
                url = ""
        source_list.append({
            "video_id": hit["video_id"],
            "channel": hit.get("channel"),
            "topic": hit.get("topic"),
            "source": hit.get("source"),
            "scene_index": hit.get("scene_index"),
            "content": hit["content"],
            "url": url,
        })
    return {"question": question, "answer": answer, "sources": source_list}


def status() -> dict[str, Any]:
    init_db()
    with _conn() as conn:
        docs = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        vectors = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE vector_json IS NOT NULL"
        ).fetchone()["n"]
    return {"documents": docs, "chunks": chunks, "vectors": vectors}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "init_db", "index_video", "index_all", "unindex", "search", "ask", "status",
    "OllamaEmbedder", "EmbeddingError", "CHUNK_HOOK", "CHUNK_SCENE", "CHUNK_OUTRO",
]