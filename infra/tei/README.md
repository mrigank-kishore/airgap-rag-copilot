# Text Embeddings Inference

This folder contains separate Dockerfiles for embeddings and reranking.

Build embeddings:

```powershell
docker build -f infra/tei/Dockerfile.embeddings -t airgap-rag/tei-embeddings:local infra/tei
```

Build reranker:

```powershell
docker build -f infra/tei/Dockerfile.reranker -t airgap-rag/tei-reranker:local infra/tei
```
