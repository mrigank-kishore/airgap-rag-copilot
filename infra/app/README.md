# Application Container

Build:

```powershell
docker build -f infra/app/Dockerfile -t airgap-rag/app:local .
```

Run:

```powershell
docker run --rm -p 8000:8000 --env-file .env airgap-rag/app:local
```
