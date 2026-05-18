from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
import typer


PARSER_VERSION = "markdown-text-v1"
CHUNKING_VERSION = "heading-word-v1"
APP_ENV = os.getenv("APP_ENV", "development").lower()
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "BAAI/bge-small-en-v1.5" if APP_ENV == "development" else "BAAI/bge-m3",
)
DEFAULT_VECTOR_SIZE = int(os.getenv("EMBEDDING_VECTOR_SIZE", "384" if APP_ENV == "development" else "1024"))
DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_TEI_URL = os.getenv("TEI_EMBEDDING_URL", "http://localhost:8080")
DEFAULT_COLLECTION = os.getenv(
    "QDRANT_COLLECTION",
    "localdoc_chunks_dev" if APP_ENV == "development" else "localdoc_chunks",
)
DEFAULT_DB_PATH = Path("storage/ingestion/ingestion.db")
DEFAULT_COLLECTION_CONFIG = Path(
    os.getenv(
        "QDRANT_COLLECTION_CONFIG",
        "infra/qdrant/collection.local.json" if APP_ENV == "development" else "infra/qdrant/collection.prod.json",
    )
)
SUPPORTED_DIRECT_EXTENSIONS = {".md", ".markdown", ".txt"}

app = typer.Typer(help="Ingest local documents into Qdrant through a local TEI embedding server.")


@dataclass(frozen=True)
class ParentSection:
    parent_id: str
    heading: str
    text: str
    parent_index: int


@dataclass(frozen=True)
class ChildChunk:
    chunk_id: str
    parent_id: str
    chunk_index: int
    heading: str
    text: str
    content_hash: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(*parts: object) -> str:
    joined = "|".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def qdrant_point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def clean_text(text: str) -> str:
    text = text.replace("\ufeff", "").replace("\u00a0", " ")
    text = text.replace("Â", "").replace("\ufffd", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_supported_file(path: Path) -> str:
    if path.suffix.lower() not in SUPPORTED_DIRECT_EXTENSIONS:
        raise ValueError(f"Unsupported extension for v1 direct parser: {path.suffix}")
    return clean_text(path.read_text(encoding="utf-8", errors="replace"))


def iter_source_files(input_dir: Path) -> Iterable[Path]:
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_DIRECT_EXTENSIONS:
            yield path


def split_parent_sections(path: Path, source_hash: str, text: str) -> list[ParentSection]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = path.stem
    current_lines: list[str] = []

    for line in text.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match and current_lines:
            sections.append((current_heading, current_lines))
            current_heading = heading_match.group(2).strip()
            current_lines = [line]
        elif heading_match:
            current_heading = heading_match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines))

    if not sections and text:
        sections = [(path.stem, [text])]

    parents: list[ParentSection] = []
    for parent_index, (heading, lines) in enumerate(sections):
        parent_text = clean_text("\n".join(lines))
        if not parent_text:
            continue
        parent_id = stable_id(
            path.as_posix(),
            source_hash,
            PARSER_VERSION,
            CHUNKING_VERSION,
            parent_index,
            heading,
        )
        parents.append(
            ParentSection(
                parent_id=parent_id,
                heading=heading,
                text=parent_text,
                parent_index=parent_index,
            )
        )
    return parents


def word_chunks(words: list[str], chunk_words: int, overlap_words: int) -> Iterable[str]:
    if chunk_words <= overlap_words:
        raise ValueError("chunk_words must be greater than overlap_words")

    step = chunk_words - overlap_words
    for start in range(0, len(words), step):
        window = words[start : start + chunk_words]
        if not window:
            continue
        yield " ".join(window)
        if start + chunk_words >= len(words):
            break


def split_child_chunks(
    source_path: Path,
    source_hash: str,
    parent: ParentSection,
    embedding_model: str,
    chunk_words: int,
    overlap_words: int,
) -> list[ChildChunk]:
    words = parent.text.split()
    raw_chunks = list(word_chunks(words, chunk_words, overlap_words)) if words else []
    if not raw_chunks and parent.text:
        raw_chunks = [parent.text]

    chunks: list[ChildChunk] = []
    for chunk_index, chunk_text in enumerate(raw_chunks):
        content_hash = sha256_text(chunk_text)
        chunk_id = stable_id(
            source_path.as_posix(),
            source_hash,
            PARSER_VERSION,
            CHUNKING_VERSION,
            embedding_model,
            parent.parent_id,
            chunk_index,
            content_hash,
        )
        chunks.append(
            ChildChunk(
                chunk_id=chunk_id,
                parent_id=parent.parent_id,
                chunk_index=chunk_index,
                heading=parent.heading,
                text=chunk_text,
                content_hash=content_hash,
            )
        )
    return chunks


class IngestionStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(db_path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.create_schema()

    def create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_files (
                source_path TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                chunking_version TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                parent_count INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS parent_documents (
                parent_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                parent_index INTEGER NOT NULL,
                heading TEXT NOT NULL,
                text TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def is_unchanged(self, source_path: Path, source_hash: str, embedding_model: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1 FROM source_files
            WHERE source_path = ?
              AND source_hash = ?
              AND parser_version = ?
              AND chunking_version = ?
              AND embedding_model = ?
            """,
            (
                source_path.as_posix(),
                source_hash,
                PARSER_VERSION,
                CHUNKING_VERSION,
                embedding_model,
            ),
        ).fetchone()
        return row is not None

    def replace_file_state(
        self,
        source_path: Path,
        source_hash: str,
        embedding_model: str,
        parents: list[ParentSection],
        chunk_count: int,
        ingested_at: str,
    ) -> None:
        source_key = source_path.as_posix()
        with self.connection:
            self.connection.execute("DELETE FROM parent_documents WHERE source_path = ?", (source_key,))
            for parent in parents:
                self.connection.execute(
                    """
                    INSERT INTO parent_documents (
                        parent_id, source_path, source_hash, parent_index, heading,
                        text, content_hash, ingested_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parent.parent_id,
                        source_key,
                        source_hash,
                        parent.parent_index,
                        parent.heading,
                        parent.text,
                        sha256_text(parent.text),
                        ingested_at,
                    ),
                )
            self.connection.execute(
                """
                INSERT INTO source_files (
                    source_path, source_name, source_hash, parser_version,
                    chunking_version, embedding_model, ingested_at,
                    parent_count, chunk_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_hash = excluded.source_hash,
                    parser_version = excluded.parser_version,
                    chunking_version = excluded.chunking_version,
                    embedding_model = excluded.embedding_model,
                    ingested_at = excluded.ingested_at,
                    parent_count = excluded.parent_count,
                    chunk_count = excluded.chunk_count
                """,
                (
                    source_key,
                    source_path.name,
                    source_hash,
                    PARSER_VERSION,
                    CHUNKING_VERSION,
                    embedding_model,
                    ingested_at,
                    len(parents),
                    chunk_count,
                ),
            )

    def close(self) -> None:
        self.connection.close()


class TeiClient:
    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def check(self) -> None:
        self.embed(["health check"])

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = requests.post(
            f"{self.base_url}/embed",
            json={"inputs": texts},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError("TEI /embed returned an unexpected response")
        if texts and data and isinstance(data[0], (int, float)):
            return [data]
        return data


class QdrantClient:
    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def check(self) -> None:
        response = requests.get(f"{self.base_url}/collections", timeout=self.timeout_seconds)
        response.raise_for_status()

    def ensure_collection(self, collection: str, config_path: Path, vector_size: int) -> None:
        response = requests.get(
            f"{self.base_url}/collections/{collection}",
            timeout=self.timeout_seconds,
        )
        if response.status_code == 200:
            details = response.json()
            actual_size = details.get("result", {}).get("config", {}).get("params", {}).get("vectors", {}).get("size")
            if actual_size != vector_size:
                raise RuntimeError(
                    f"Collection {collection} has vector size {actual_size}, but ingestion expects {vector_size}. "
                    "Use a separate collection for each embedding model dimension."
                )
            return
        if response.status_code != 404:
            response.raise_for_status()

        config = json.loads(config_path.read_text(encoding="utf-8"))
        create_response = requests.put(
            f"{self.base_url}/collections/{collection}",
            json=config,
            timeout=self.timeout_seconds,
        )
        create_response.raise_for_status()

    def upsert_points(self, collection: str, points: list[dict]) -> None:
        if not points:
            return
        response = requests.put(
            f"{self.base_url}/collections/{collection}/points",
            params={"wait": "true"},
            json={"points": points},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def delete_source_points(self, collection: str, source_path: Path) -> None:
        response = requests.post(
            f"{self.base_url}/collections/{collection}/points/delete",
            params={"wait": "true"},
            json={
                "filter": {
                    "must": [
                        {
                            "key": "source_path",
                            "match": {"value": source_path.as_posix()},
                        }
                    ]
                }
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()


def batched(values: list[ChildChunk], batch_size: int) -> Iterable[list[ChildChunk]]:
    for index in range(0, len(values), batch_size):
        yield values[index : index + batch_size]


@app.command()
def main(
    input_dir: Path = typer.Option(Path("data/raw"), "--input", "-i", help="Directory of source files."),
    collection: str = typer.Option(DEFAULT_COLLECTION, "--collection", "-c", help="Qdrant collection name."),
    qdrant_url: str = typer.Option(DEFAULT_QDRANT_URL, "--qdrant-url", help="Qdrant HTTP URL."),
    tei_url: str = typer.Option(DEFAULT_TEI_URL, "--tei-url", help="TEI HTTP URL."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite ingestion state path."),
    embedding_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, "--embedding-model", help="Embedding model name for metadata."),
    collection_config: Path = typer.Option(DEFAULT_COLLECTION_CONFIG, "--collection-config", help="Qdrant collection JSON config."),
    vector_size: int = typer.Option(DEFAULT_VECTOR_SIZE, "--vector-size", help="Expected embedding vector size."),
    chunk_words: int = typer.Option(700, "--chunk-words", help="Target chunk size in words."),
    overlap_words: int = typer.Option(100, "--overlap-words", help="Chunk overlap in words."),
    batch_size: int = typer.Option(16, "--batch-size", help="Embedding/upsert batch size."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", help="HTTP timeout for TEI and Qdrant."),
    force: bool = typer.Option(False, "--force", help="Re-index unchanged files."),
) -> None:
    """Ingest supported local files into Qdrant."""
    if not input_dir.exists():
        raise typer.BadParameter(f"Input directory does not exist: {input_dir}")
    if not collection_config.exists():
        raise typer.BadParameter(f"Collection config does not exist: {collection_config}")

    qdrant = QdrantClient(qdrant_url, timeout_seconds)
    tei = TeiClient(tei_url, timeout_seconds)
    store = IngestionStore(db_path)

    try:
        typer.echo(f"Checking Qdrant at {qdrant_url}...")
        qdrant.check()
        qdrant.ensure_collection(collection, collection_config, vector_size)

        typer.echo(f"Checking TEI at {tei_url}...")
        tei.check()

        files = list(iter_source_files(input_dir))
        typer.echo(f"Discovered {len(files)} supported source file(s) under {input_dir}.")

        total_indexed_files = 0
        total_skipped_files = 0
        total_chunks = 0

        for source_path in files:
            source_hash = sha256_file(source_path)
            if not force and store.is_unchanged(source_path, source_hash, embedding_model):
                typer.echo(f"Skipped unchanged file: {source_path}")
                total_skipped_files += 1
                continue

            text = read_supported_file(source_path)
            parents = split_parent_sections(source_path, source_hash, text)
            chunks: list[ChildChunk] = []
            for parent in parents:
                chunks.extend(
                    split_child_chunks(
                        source_path=source_path,
                        source_hash=source_hash,
                        parent=parent,
                        embedding_model=embedding_model,
                        chunk_words=chunk_words,
                        overlap_words=overlap_words,
                    )
                )

            ingested_at = utc_now()
            qdrant.delete_source_points(collection, source_path)
            for chunk_batch in batched(chunks, batch_size):
                vectors = tei.embed([chunk.text for chunk in chunk_batch])
                if len(vectors) != len(chunk_batch):
                    raise RuntimeError("TEI embedding count did not match chunk count")

                points = []
                for chunk, vector in zip(chunk_batch, vectors):
                    if len(vector) != vector_size:
                        raise RuntimeError(
                            f"Expected {vector_size}-dimensional embedding from {embedding_model}, got {len(vector)}"
                        )
                    points.append(
                        {
                            "id": qdrant_point_id(chunk.chunk_id),
                            "vector": vector,
                            "payload": {
                                "source_path": source_path.as_posix(),
                                "source_name": source_path.name,
                                "source_hash": source_hash,
                                "parent_id": chunk.parent_id,
                                "chunk_id": chunk.chunk_id,
                                "chunk_index": chunk.chunk_index,
                                "heading": chunk.heading,
                                "text": chunk.text,
                                "content_hash": chunk.content_hash,
                                "parser_version": PARSER_VERSION,
                                "chunking_version": CHUNKING_VERSION,
                                "embedding_model": embedding_model,
                                "ingested_at": ingested_at,
                            },
                        }
                    )
                qdrant.upsert_points(collection, points)

            store.replace_file_state(
                source_path=source_path,
                source_hash=source_hash,
                embedding_model=embedding_model,
                parents=parents,
                chunk_count=len(chunks),
                ingested_at=ingested_at,
            )
            typer.echo(f"Indexed {source_path}: {len(parents)} parent(s), {len(chunks)} chunk(s)")
            total_indexed_files += 1
            total_chunks += len(chunks)

        typer.echo(
            f"Done. Indexed {total_indexed_files} file(s), skipped {total_skipped_files}, upserted {total_chunks} chunk(s)."
        )
    finally:
        store.close()


if __name__ == "__main__":
    app()
