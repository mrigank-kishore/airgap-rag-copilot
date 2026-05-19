from __future__ import annotations

import textwrap
import sqlite3
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

import requests
import typer


DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_TEI_URL = os.getenv("TEI_EMBEDDING_URL", "http://localhost:8080")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "localdoc_chunks_dev")
DEFAULT_DB_PATH = Path(os.getenv("INGESTION_DB", "storage/ingestion/ingestion.db"))
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

app = typer.Typer(help="Run one-shot and agentic RAG against local Qdrant + TEI + vLLM.")


@dataclass(frozen=True)
class SearchHit:
    score: float
    payload: dict


@dataclass(frozen=True)
class ParentDocument:
    parent_id: str
    source_path: str
    heading: str
    text: str


@dataclass(frozen=True)
class RetrievedPassage:
    parent_id: str
    source_path: str
    heading: str
    text: str
    score: float


class TeiClient:
    def __init__(self, base_url: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = requests.post(
            f"{self.base_url}/embed",
            json={"inputs": texts},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError("TEI /embed returned unexpected payload")
        if texts and data and isinstance(data[0], (int, float)):
            return [data]
        return data

    def rerank(self, query: str, candidates: List[str]) -> List[float]:
        if not candidates:
            return []
        response = requests.post(
            f"{self.base_url}/rerank",
            json={"query": query, "candidates": candidates},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or len(data) != len(candidates):
            raise RuntimeError("TEI /rerank returned unexpected payload")
        return [float(x) for x in data]


class QdrantClient:
    def __init__(self, base_url: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, collection: str, vector: List[float], limit: int = 50) -> List[SearchHit]:
        body = {"vector": vector, "limit": limit, "with_payload": True}
        response = requests.post(
            f"{self.base_url}/collections/{collection}/points/search",
            json=body,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        hits: List[SearchHit] = []
        for item in data.get("result", []):
            score = float(item.get("score", 0.0))
            payload = item.get("payload", {}) or {}
            hits.append(SearchHit(score=score, payload=payload))
        return hits


class IngestionStore:
    def __init__(self, db_path: Path) -> None:
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row

    def fetch_parents(self, parent_ids: List[str]) -> dict:
        if not parent_ids:
            return {}
        placeholders = ",".join("?" for _ in parent_ids)
        query = f"""
            SELECT parent_id, source_path, heading, text
            FROM parent_documents
            WHERE parent_id IN ({placeholders})
        """
        rows = self.connection.execute(query, parent_ids).fetchall()
        return {
            row["parent_id"]: ParentDocument(
                parent_id=row["parent_id"],
                source_path=row["source_path"],
                heading=row["heading"],
                text=row["text"],
            )
            for row in rows
        }

    def close(self) -> None:
        self.connection.close()


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def complete(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> str:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a grounded retrieval augmented generation assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "stream": False,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {})
        return message.get("content", "").strip()


def build_prompt(query: str, passages: List[RetrievedPassage]) -> str:
    if not passages:
        return (
            "You have no retrieved passages. Answer the question only if the answer clearly appears "
            "in the provided documents. Otherwise say: 'I could not find a definitive answer in the documents.'\n\n"
            f"QUESTION: {query}"
        )

    blocks = []
    for index, passage in enumerate(passages, start=1):
        snippet = textwrap.shorten(passage.text, width=1400, placeholder="...")
        blocks.append(
            f"PASSAGE {index}\nSource: {passage.source_path}\nHeading: {passage.heading}\nScore: {passage.score:.4f}\n{snippet}"
        )

    # Encourage extraction of concise definitions when present. If any passage contains a
    # definitional sentence (for example contains 'is a'/'is an' or 'refers to'), produce a
    # short definition (1-3 sentences) using only the passages and cite the single best
    # source (source path + heading). Otherwise, if no clear answer is present, reply
    # exactly with: 'I could not find a definitive answer in the documents.'
    return (
        "Use only the information from the retrieved passages below. Do not hallucinate.\n\n"
        "If any passage contains a clear definitional sentence (for example: 'X is a', 'X is an', "
        "or 'X refers to'), produce a concise definition (1-3 short sentences) and CITE the single best source "
        "using the source path and heading (format: '- <source>\n  - Heading: <heading>').\n\n"
        "If the passages do not contain a clear definitional statement, respond with exactly: 'I could not find a definitive answer in the documents.'\n\n"
        f"QUESTION: {query}\n\nRETRIEVED PASSAGES:\n\n"
        + "\n\n".join(blocks)
    )


def collapse_by_parent(hits: List[SearchHit], parents: dict) -> List[RetrievedPassage]:
    seen = set()
    passages: List[RetrievedPassage] = []
    for hit in hits:
        parent_id = str(hit.payload.get("parent_id", ""))
        if not parent_id or parent_id in seen:
            continue
        parent = parents.get(parent_id)
        if parent is None:
            continue
        passages.append(
            RetrievedPassage(
                parent_id=parent.parent_id,
                source_path=parent.source_path,
                heading=parent.heading,
                text=parent.text,
                score=hit.score,
            )
        )
        seen.add(parent_id)
    return passages


def rerank_passages(tei: TeiClient, query: str, passages: List[RetrievedPassage], use_reranker: bool) -> List[RetrievedPassage]:
    if not use_reranker or not passages:
        return passages
    candidate_texts = [p.text for p in passages]
    try:
        scores = tei.rerank(query, candidate_texts)
    except Exception:
        return passages
    if len(scores) != len(passages):
        return passages
    ranked = sorted(zip(scores, passages), key=lambda item: item[0], reverse=True)
    return [p for _, p in ranked]


def one_shot_rag(query: str, qdrant: QdrantClient, tei: TeiClient, ingestion: IngestionStore, collection: str, search_limit: int, top_passages: int, use_reranker: bool) -> str:
    embedding = tei.embed([query])[0]
    hits = qdrant.search(collection=collection, vector=embedding, limit=search_limit)
    parent_ids = [str(hit.payload.get("parent_id", "")) for hit in hits if hit.payload.get("parent_id")]
    parents = ingestion.fetch_parents(parent_ids)
    passages = collapse_by_parent(hits, parents)[:top_passages]
    passages = rerank_passages(tei=tei, query=query, passages=passages, use_reranker=use_reranker)
    prompt = build_prompt(query=query, passages=passages)
    ollama = OllamaClient(base_url=DEFAULT_OLLAMA_URL, model=DEFAULT_OLLAMA_MODEL)
    return ollama.complete(prompt=prompt)


def should_refine(answer: str) -> bool:
    lower = answer.lower()
    if "i could not find" in lower or "not found" in lower or "insufficient" in lower:
        return True
    return False


def refine_query(original_query: str, previous_answer: str, passages: List[RetrievedPassage], vllm: OllamaClient) -> str:
    context = "\n\n".join(f"- {p.source_path} | {p.heading}" for p in passages[:5])
    prompt = (
        "You are a retrieval assistant that refines search queries. "
        "Given the user's original question, the prior answer, and the sources used, "
        "produce a better query for a follow-up retrieval step if the answer is incomplete. "
        "If the prior answer is sufficient and no refinement is needed, reply with exactly:\n"
        "NO_REFINEMENT_NEEDED\n\n"
        f"Original question: {original_query}\n"
        f"Previous answer: {previous_answer}\n"
        f"Sources: {context}\n\n"
        "Give a short search query only."
    )
    candidate = vllm.complete(prompt=prompt, max_tokens=128, temperature=0.2).strip()
    if candidate.upper().startswith("NO_REFINEMENT_NEEDED"):
        return ""
    return candidate


def agentic_rag(query: str, qdrant: QdrantClient, tei: TeiClient, ingestion: IngestionStore, collection: str, search_limit: int, top_passages: int, use_reranker: bool, max_iterations: int) -> str:
    ollama = OllamaClient(base_url=DEFAULT_OLLAMA_URL, model=DEFAULT_OLLAMA_MODEL)
    current_query = query
    last_answer = ""
    for iteration in range(1, max_iterations + 1):
        answer = one_shot_rag(
            query=current_query,
            qdrant=qdrant,
            tei=tei,
            ingestion=ingestion,
            collection=collection,
            search_limit=search_limit,
            top_passages=top_passages,
            use_reranker=use_reranker,
        )
        if not should_refine(answer):
            return answer
        if iteration == max_iterations:
            return answer

        embedding = tei.embed([query])[0]
        hits = qdrant.search(collection=collection, vector=embedding, limit=search_limit)
        parents = ingestion.fetch_parents([str(hit.payload.get("parent_id", "")) for hit in hits])
        passages = collapse_by_parent(hits, parents)[:top_passages]
        next_query = refine_query(original_query=query, previous_answer=answer, passages=passages, vllm=ollama)
        if not next_query or next_query == current_query:
            return answer
        current_query = next_query
        last_answer = answer

    return last_answer or "I could not find a definitive answer in the documents."


@app.command()
def query(
    question: str = typer.Argument(..., help="User query to answer."),
    collection: str = typer.Option(DEFAULT_COLLECTION, "--collection", "-c", help="Qdrant collection name."),
    qdrant_url: str = typer.Option(DEFAULT_QDRANT_URL, "--qdrant-url", help="Qdrant HTTP URL."),
    tei_url: str = typer.Option(DEFAULT_TEI_URL, "--tei-url", help="TEI HTTP URL."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite ingestion state path."),
    use_reranker: bool = typer.Option(True, "--use-reranker/--no-reranker", help="Use TEI reranker if available."),
    agentic: bool = typer.Option(False, "--agentic", help="Run the agentic RAG loop."),
    max_iterations: int = typer.Option(3, "--max-iterations", help="Maximum agentic iterations."),
    search_limit: int = typer.Option(50, "--search-limit", help="Number of child chunks to retrieve from Qdrant."),
    top_passages: int = typer.Option(10, "--top-passages", help="Number of final passages to pass to the LLM."),
) -> None:
    """Answer a question using local Qdrant + TEI + vLLM."""
    qdrant = QdrantClient(qdrant_url)
    tei = TeiClient(tei_url)
    ingestion = IngestionStore(db_path)

    try:
        if agentic:
            answer = agentic_rag(
                query=question,
                qdrant=qdrant,
                tei=tei,
                ingestion=ingestion,
                collection=collection,
                search_limit=search_limit,
                top_passages=top_passages,
                use_reranker=use_reranker,
                max_iterations=max_iterations,
            )
        else:
            answer = one_shot_rag(
                query=question,
                qdrant=qdrant,
                tei=tei,
                ingestion=ingestion,
                collection=collection,
                search_limit=search_limit,
                top_passages=top_passages,
                use_reranker=use_reranker,
            )
        typer.echo("\n=== ANSWER ===\n")
        typer.echo(answer)
    finally:
        ingestion.close()


if __name__ == "__main__":
    app()
