docker build -f infra/tei/Dockerfile.embeddings -t airgap-rag/tei-embeddings:local infra/tei
docker run --rm `
  --name airgap-rag-tei-embeddings `
  -p 8080:80 `
  -v "${PWD}/models/embeddings:/models" `
  airgap-rag/tei-embeddings:local
