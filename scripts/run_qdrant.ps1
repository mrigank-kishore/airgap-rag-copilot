param(
    [string]$Image = "airgap-rag/qdrant:local",
    [string]$ContainerName = "airgap-rag-qdrant-local"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$storagePath = Join-Path $repoRoot "storage\qdrant"
$snapshotsPath = Join-Path $repoRoot "storage\qdrant-snapshots"

New-Item -ItemType Directory -Force -Path $storagePath | Out-Null
New-Item -ItemType Directory -Force -Path $snapshotsPath | Out-Null

docker build -f (Join-Path $repoRoot "infra\qdrant\Dockerfile.local") `
  -t $Image `
  (Join-Path $repoRoot "infra\qdrant")

docker run --rm `
  --name $ContainerName `
  -p 6333:6333 `
  -p 6334:6334 `
  -v "${storagePath}:/qdrant/storage" `
  -v "${snapshotsPath}:/qdrant/snapshots" `
  $Image
