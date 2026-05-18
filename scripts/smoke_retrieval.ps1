param(
    [string]$Question = "What is RobotStudio?",
    [string]$Collection = "localdoc_chunks_dev",
    [string]$TeiUrl = "http://localhost:8080",
    [string]$QdrantUrl = "http://localhost:6333",
    [int]$Limit = 5
)

$ErrorActionPreference = "Stop"

$embedBody = @{
    inputs = $Question
} | ConvertTo-Json

$embeddingResponse = Invoke-RestMethod `
    -Method Post `
    -Uri "$TeiUrl/embed" `
    -ContentType "application/json" `
    -Body $embedBody

$vector = if ($embeddingResponse[0] -is [array]) {
    $embeddingResponse[0]
} else {
    $embeddingResponse
}

$searchBody = @{
    vector       = $vector
    limit        = $Limit
    with_payload = $true
} | ConvertTo-Json -Depth 100

$searchResponse = Invoke-RestMethod `
    -Method Post `
    -Uri "$QdrantUrl/collections/$Collection/points/search" `
    -ContentType "application/json" `
    -Body $searchBody

Write-Host ""
Write-Host "Question: $Question"
Write-Host "Collection: $Collection"
Write-Host ""

$rank = 1
foreach ($hit in $searchResponse.result) {
    $payload = $hit.payload
    $preview = $payload.text
    if ($preview.Length -gt 700) {
        $preview = $preview.Substring(0, 700)
    }

    Write-Host "#$rank score=$($hit.score)"
    Write-Host "source=$($payload.source_path)"
    Write-Host "heading=$($payload.heading)"
    Write-Host $preview
    Write-Host ""

    $rank += 1
}
