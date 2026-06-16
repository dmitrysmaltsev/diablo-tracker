# Serve the D4 Gear Tracker locally.
#   .\serve.ps1            -> http://localhost:8000
#   .\serve.ps1 -Port 9000 -> custom port
#   .\serve.ps1 -Open      -> also open the browser
param(
    [int]$Port = 8000,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$url = "http://localhost:$Port"
Write-Host "Serving $PSScriptRoot at $url  (Ctrl+C to stop)" -ForegroundColor Yellow
if ($Open) { Start-Process $url }

if (Get-Command python -ErrorAction SilentlyContinue) {
    python -m http.server $Port
}
elseif (Get-Command npx -ErrorAction SilentlyContinue) {
    npx --yes serve -l $Port
}
else {
    Write-Error "Neither 'python' nor 'npx' found. Install Python or Node to serve locally."
}
