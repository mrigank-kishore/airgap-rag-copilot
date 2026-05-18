# Qdrant

This folder contains independent Qdrant container definitions for local development and production-style deployment.

## Local

Build:

```powershell
docker build -f infra/qdrant/Dockerfile.local -t airgap-rag/qdrant:local infra/qdrant
```

Run:

```powershell
docker run --rm `
  --name airgap-rag-qdrant-local `
  -p 6333:6333 `
  -p 6334:6334 `
  -v "${PWD}/storage/qdrant:/qdrant/storage" `
  -v "${PWD}/storage/qdrant-snapshots:/qdrant/snapshots" `
  airgap-rag/qdrant:local
```

Local mode is intentionally simple:

- Latest Qdrant image
- Local persisted storage under `storage/qdrant`
- Local snapshots under `storage/qdrant-snapshots`
- HTTP on `localhost:6333`
- gRPC on `localhost:6334`

## Production

Build:

```powershell
docker build -f infra/qdrant/Dockerfile.prod -t airgap-rag/qdrant:prod infra/qdrant
```

Run:

```powershell
docker run -d `
  --name airgap-rag-qdrant-prod `
  -p 6333:6333 `
  -p 6334:6334 `
  -v "${PWD}/storage/qdrant:/qdrant/storage" `
  -v "${PWD}/storage/qdrant-snapshots:/qdrant/snapshots" `
  --restart unless-stopped `
  airgap-rag/qdrant:prod
```

Production mode changes:

- Uses `config.prod.yaml`
- Disables CORS
- Enables on-disk payload storage
- Separates snapshots from database storage
- Keeps telemetry disabled for closed environments

## Production Collection Template

Create the production collection after Qdrant is running:

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri http://localhost:6333/collections/localdoc_chunks `
  -ContentType "application/json" `
  -InFile infra/qdrant/collection.prod.json
```

The production collection template enables:

- 1024-dimensional vectors for BGE-M3
- cosine distance
- on-disk vectors
- on-disk HNSW
- Int8 scalar quantization

Tune `hnsw_config`, segment count, and quantization settings after benchmarking with your real document corpus.
