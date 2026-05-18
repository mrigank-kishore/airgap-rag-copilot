docker build -f infra/vllm/Dockerfile -t airgap-rag/vllm:local infra/vllm
docker run --rm `
  --name airgap-rag-vllm `
  --gpus all `
  -p 8001:8000 `
  -v "${PWD}/models/llm:/models" `
  airgap-rag/vllm:local `
  --model /models
