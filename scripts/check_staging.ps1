param(
  [string]$ApiUrl = $env:APFLOW_API_BASE_URL,
  [string]$WebUrl = $env:APFLOW_WEB_BASE_URL,
  [string]$EnvFile = $(if ($env:ENV_FILE) { $env:ENV_FILE } else { ".env.staging" }),
  [switch]$SkipUpload,
  [switch]$SkipVendor
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if ([string]::IsNullOrWhiteSpace($ApiUrl) -or [string]::IsNullOrWhiteSpace($WebUrl)) {
  throw "Usage: scripts/check_staging.ps1 -ApiUrl https://api.example.com -WebUrl https://app.example.com"
}

if (!(Test-Path $EnvFile)) {
  throw "Missing $EnvFile. Set -EnvFile or copy .env.staging.example to .env.staging."
}

$env:APFLOW_ENV_FILE = $EnvFile
$compose = @("compose", "-f", "docker-compose.yml", "-f", "docker-compose.staging.yml", "--env-file", $EnvFile)

Write-Host "Checking Docker daemon..."
docker info | Out-Null

Write-Host "Checking Compose configuration..."
docker @compose config --quiet

Write-Host "Checking running containers..."
docker @compose ps
docker @compose ps --status running api web postgres redis | Out-Null

Write-Host "Checking PostgreSQL data directory..."
docker @compose exec -T postgres sh -c "test -d /var/lib/postgresql/data/base"

Write-Host "Checking API health and readiness..."
Invoke-WebRequest "$ApiUrl/health" -UseBasicParsing | Out-Null
Invoke-WebRequest "$ApiUrl/ready" -UseBasicParsing | Out-Null

Write-Host "Checking web URL..."
Invoke-WebRequest $WebUrl -UseBasicParsing | Out-Null

$verify = @("scripts/verify_runtime.py", "--api-url", $ApiUrl, "--web-url", $WebUrl, "--auth-enabled")
if ($env:APFLOW_VERIFY_EMAIL) {
  $verify += @("--email", $env:APFLOW_VERIFY_EMAIL)
}
if ($env:APFLOW_VERIFY_PASSWORD) {
  $verify += @("--password", $env:APFLOW_VERIFY_PASSWORD)
}
if ($SkipUpload) {
  $verify += "--skip-upload"
}
if ($SkipVendor) {
  $verify += "--skip-vendor"
}
python @verify
