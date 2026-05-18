# Airgap RAG Copilot

Production-ready RAG system for closed, air-gapped environments with no recurring SaaS or per-token API cost.

This project is an on-premises local document copilot for private document search over large local corpora.

See [OFFLINE_RAG_PRODUCTION_STACK.md](OFFLINE_RAG_PRODUCTION_STACK.md) for the production stack, sizing guidance, and architecture notes.

## Run Individual Components

Each runtime component has its own Dockerfile under `infra/`.

Run Qdrant only:

```powershell
scripts/run_qdrant.ps1
```

Qdrant will be available at:

```text
http://localhost:6333
```

Run TEI embeddings for local development with BGE small:

```powershell
scripts/run_tei_embeddings.ps1
```

TEI will be available at:

```text
http://localhost:8080
```

If NVIDIA Docker is not available, a slower CPU fallback is available:

```powershell
scripts/run_tei_embeddings_cpu.ps1
```

## Ingest Local Documents

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

With Qdrant and TEI running, ingest files from `data/raw`:

```powershell
python -m app.ingest `
  --input data/raw `
  --collection localdoc_chunks_dev `
  --embedding-model BAAI/bge-small-en-v1.5 `
  --collection-config infra/qdrant/collection.local.json `
  --vector-size 384
```

Production ingestion uses BGE-M3 and the production Qdrant collection config:

```powershell
scripts/run_tei_embeddings.ps1 -Model BAAI/bge-m3

python -m app.ingest `
  --input data/raw `
  --collection localdoc_chunks `
  --embedding-model BAAI/bge-m3 `
  --collection-config infra/qdrant/collection.prod.json `
  --vector-size 1024
```

The ingestion CLI:

- Parses `.md`, `.markdown`, and `.txt` files directly.
- Chunks by Markdown headings, then into overlapping child chunks.
- Embeds chunks through TEI at `http://localhost:8080`.
- Creates or reuses the Qdrant collection configured by the selected collection JSON.
- Stores parent sections and incremental indexing state in `storage/ingestion/ingestion.db`.

Re-run the same command to skip unchanged files. Use `--force` to re-index anyway.
