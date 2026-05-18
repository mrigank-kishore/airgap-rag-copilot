docker build -f infra/app/Dockerfile -t airgap-rag/app:local .
docker run --rm `
  --name airgap-rag-app `
  -p 8000:8000 `
  --env-file .env `
  airgap-rag/app:local
