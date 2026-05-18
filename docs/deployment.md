# Deployment

This project uses separate Dockerfiles for each runtime component.

## Component Dockerfiles

| Component | Dockerfile |
|---|---|
| Application API | `infra/app/Dockerfile` |
| Qdrant | `infra/qdrant/Dockerfile` |
| TEI embeddings | `infra/tei/Dockerfile.embeddings` |
| TEI reranker | `infra/tei/Dockerfile.reranker` |
| vLLM | `infra/vllm/Dockerfile` |
| Langfuse | `infra/langfuse/Dockerfile` |

## Local Run Helpers

PowerShell helper scripts are available in `scripts/`:

- `scripts/run_qdrant.ps1`
- `scripts/run_app.ps1`
- `scripts/run_tei_embeddings.ps1`
- `scripts/run_tei_reranker.ps1`
- `scripts/run_vllm.ps1`

Each script builds and runs one component independently.
