# Langfuse

Build:

```powershell
docker build -f infra/langfuse/Dockerfile -t airgap-rag/langfuse:local infra/langfuse
```

Langfuse also requires its database and supporting runtime configuration in production. Keep that configuration local to this folder as the deployment matures.
