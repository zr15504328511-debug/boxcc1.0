"""Ingest markdown/text KB seed files into a local ChromaDB collection."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from config.paths import get_data_dir, resolve_path

SUPPORTED_SUFFIXES = {".md", ".txt"}
MIN_CHARS = 500
MAX_CHARS = 1500


def resolve_cli_path(path: str) -> Path:
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    return resolve_path(path)


def doc_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem


def split_chunks(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def emit_piece(piece: str) -> None:
        for start in range(0, len(piece), MAX_CHARS):
            part = piece[start : start + MAX_CHARS].strip()
            if part:
                chunks.append(part)

    for paragraph in paragraphs:
        if len(paragraph) > MAX_CHARS:
            if current:
                chunks.append(current.strip())
                current = ""
            emit_piece(paragraph)
            continue
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= MAX_CHARS:
            current = candidate
            continue
        if len(current) >= MIN_CHARS:
            chunks.append(current.strip())
            current = paragraph
        else:
            chunks.append(candidate.strip())
            current = ""

    if current:
        chunks.append(current.strip())
    return chunks


def stable_id(kb_id: str, rel_path: str, idx: int, content: str) -> str:
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:12]
    safe_path = re.sub(r"[^A-Za-z0-9_.-]+", "_", rel_path)
    return f"{kb_id}:{safe_path}:{idx}:{digest}"


def ingest(kb_id: str, source_dir: Path, chroma_path: Path) -> int:
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name=kb_id,
        embedding_function=embedding_functions.DefaultEmbeddingFunction(),
    )
    total = 0

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        rel_path = path.relative_to(source_dir).as_posix()
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue

        try:
            collection.delete(where={"source": rel_path})
        except Exception:
            pass

        title = doc_title(text, path)
        chunks = split_chunks(text)
        if not chunks:
            continue

        ids = [stable_id(kb_id, rel_path, i, chunk) for i, chunk in enumerate(chunks)]
        metadatas = [
            {"source": rel_path, "doc_title": title, "chunk_idx": i}
            for i, _chunk in enumerate(chunks)
        ]
        collection.add(ids=ids, documents=chunks, metadatas=metadatas)
        total += len(chunks)

    print(f"{kb_id}: ingested {total} chunk(s) into {chroma_path}")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-id", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--path", default=None, help="Chroma persistence path; defaults to data/kb/{kb_id}")
    args = parser.parse_args()

    source_dir = resolve_cli_path(args.source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"source-dir not found or not a directory: {source_dir}")

    chroma_path = resolve_cli_path(args.path) if args.path else get_data_dir() / "kb" / args.kb_id
    ingest(args.kb_id, source_dir, chroma_path)


if __name__ == "__main__":
    main()
