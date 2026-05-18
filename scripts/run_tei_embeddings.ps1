param(
    [string]$Model = "BAAI/bge-small-en-v1.5",
    [string]$Image = "ghcr.io/huggingface/text-embeddings-inference:89-1.9",
    [string]$ContainerName = "airgap-rag-tei-embeddings",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$cachePath = Join-Path $repoRoot "models\embeddings"
New-Item -ItemType Directory -Force -Path $cachePath | Out-Null

docker run --rm `
  --name $ContainerName `
  --gpus all `
  -p "${Port}:80" `
  -v "${cachePath}:/data" `
  --pull always `
  $Image `
  --model-id $Model
