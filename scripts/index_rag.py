"""
scripts/index_rag.py -- Build/maintain the transcript RAG index (CLI).

Indexes produced videos' scripts (from content_db metadata_json["script"])
into the local hybrid FTS5 + Ollama-vector store (core/rag_index.py). Also
lets you search and ask from the command line for quick verification.

Usage:
    python scripts/index_rag.py --all
    python scripts/index_rag.py --all --rebuild        # re-index everything
    python scripts/index_rag.py --all --reset          # wipe store first
    python scripts/index_rag.py --video-id 14
    python scripts/index_rag.py --channel finance
    python scripts/index_rag.py --status
    python scripts/index_rag.py --search "index funds"
    python scripts/index_rag.py --ask "What did we produce about compounding?"
    python scripts/index_rag.py --unindex 14
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Repo-root bootstrap so `python scripts/index_rag.py` can import core/config.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/maintain the transcript RAG index.")
    parser.add_argument("--all", action="store_true", help="Index every video with a script")
    parser.add_argument("--video-id", type=int, help="Index a single video id")
    parser.add_argument("--unindex", type=int, help="Remove a video id from the index")
    parser.add_argument("--channel", help="Restrict indexing/search to one channel")
    parser.add_argument("--rebuild", action="store_true", help="Re-index already-indexed videos")
    parser.add_argument("--reset", action="store_true", help="Wipe the whole store before indexing")
    parser.add_argument("--status", action="store_true", help="Show index stats")
    parser.add_argument("--search", help="Keyword/semantic search query")
    parser.add_argument("--ask", help="Question-answering query (uses the chat LLM)")
    parser.add_argument("--top-k", type=int, default=5, help="Result count for search/ask")
    args = parser.parse_args()

    from core import rag_index

    if args.status:
        print(json.dumps(rag_index.status(), indent=2))
        return
    if args.search:
        for hit in rag_index.search(args.search, top_k=args.top_k, channel=args.channel):
            print(
                f"[{hit['score']:.3f}] video {hit['video_id']} "
                f"({hit.get('channel')}) [{hit.get('source')} "
                f"scene={hit.get('scene_index')}] {hit['content'][:160]}"
            )
        return
    if args.ask:
        resp = rag_index.ask(args.ask, sources=args.top_k)
        print(f"Q: {resp['question']}")
        print(f"A: {resp['answer']}")
        for src in resp["sources"]:
            print(f"  - video {src['video_id']} [{src.get('source')}]: {src['content'][:160]}")
        return
    if args.unindex is not None:
        print("unindexed" if rag_index.unindex(args.unindex) else "not present")
        return
    if args.video_id is not None:
        print(json.dumps(rag_index.index_video(args.video_id), indent=2))
        return
    if args.all:
        print(json.dumps(
            rag_index.index_all(channel=args.channel, rebuild=args.rebuild, reset=args.reset),
            indent=2,
        ))
        return
    parser.print_help()


if __name__ == "__main__":
    main()