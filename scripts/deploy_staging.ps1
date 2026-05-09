param(
  [string]$EnvFile = ".env.staging",
  [switch]$Proxy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:APFLOW_ENV_FILE = $EnvFile

if (!(Test-Path $EnvFile)) {
  throw "Missing $EnvFile. Copy .env.staging.example to $EnvFile and replace every secret first."
}

if ((Get-Content $EnvFile -Raw) -match "replace-with") {
  throw "$EnvFile still contains replace-with placeholders."
}

$compose = @("compose", "-f", "docker-compose.yml", "-f", "docker-compose.staging.yml", "--env-file", $EnvFile)
if ($Proxy) {
  $compose += @("--profile", "proxy")
}

Write-Host "Validating Compose configuration..."
docker @compose config --quiet

Write-Host "Building and starting staging stack..."
docker @compose up --build -d

docker @compose ps
Write-Host "Deployment started. Run scripts/check_staging.ps1 after DNS/HTTPS is reachable."
