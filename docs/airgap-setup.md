# Air-Gap Setup

Offline artifact, model, package, and container preparation.

For air-gapped deployment, build each component image separately and export it as a tar archive:

```powershell
docker save airgap-rag/qdrant:local -o artifacts/airgap-rag-qdrant.tar
```

On the offline host, import the image:

```powershell
docker load -i artifacts/airgap-rag-qdrant.tar
```
