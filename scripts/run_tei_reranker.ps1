docker build -f infra/tei/Dockerfile.reranker -t airgap-rag/tei-reranker:local infra/tei
docker run --rm `
  --name airgap-rag-tei-reranker `
  -p 8081:80 `
  -v "${PWD}/models/rerankers:/models" `
  airgap-rag/tei-reranker:local
