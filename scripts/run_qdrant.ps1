docker build -f infra/qdrant/Dockerfile -t airgap-rag/qdrant:local infra/qdrant
docker run --rm `
  --name airgap-rag-qdrant `
  -p 6333:6333 `
  -p 6334:6334 `
  -v "${PWD}/storage/qdrant:/qdrant/storage" `
  airgap-rag/qdrant:local
