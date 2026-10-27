<#
.SYNOPSIS
  Install the Lognexa endpoint agent as a Windows service (auto-start).
.DESCRIPTION
  Creates C:\Program Files\Lognexa Agent, a virtual environment, installs the
  agent, writes the config, enrols with the supplied token and registers a
  service that restarts automatically. Run from an elevated PowerShell prompt.
.EXAMPLE
  .\install-windows.ps1 -ServerUrl "https://lognexa.example.com:8000" -EnrollToken "lnx_..."
.NOTES
  Double-clicking a .ps1 opens it in Notepad instead of running it. Use the
  install-windows.cmd wrapper in this folder for a double-clickable, self-
  elevating install, or run this script from an elevated PowerShell prompt.
#>
param(
  [Parameter(Mandatory = $true)][string]$ServerUrl,
  [Parameter(Mandatory = $true)][string]$EnrollToken,
  [string]$InstallDir = "$env:ProgramFiles\Lognexa Agent",
  [string]$CaBundle = "",
  [switch]$AllowHttp
)

$ErrorActionPreference = "Stop"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
  throw "This installer must be run as Administrator (needed to read the Security event log and register a service)."
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "Python 3.9+ is required on PATH." }

Write-Host "Installing to $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force "$PSScriptRoot\..\*" $InstallDir -Exclude @("deploy")

& $python -m venv "$InstallDir\venv"
& "$InstallDir\venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$InstallDir\venv\Scripts\python.exe" -m pip install --quiet "$InstallDir"

$dataDir = "$env:ProgramData\Lognexa\agent"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
# Plain HTTP is accepted only for a localhost dev server (enforced by the client).
# Enable it automatically for an http:// URL, or when -AllowHttp is passed, and
# persist it so the service (which reads config.json, not CLI flags) agrees.
$allowHttp = [bool]$AllowHttp -or ($ServerUrl -like "http://*")
$config = @{
  server_url       = $ServerUrl
  verify_tls       = if ($CaBundle) { $CaBundle } else { $true }
  insecure_http_ok = $allowHttp
} | ConvertTo-Json
Set-Content -Path "$dataDir\config.json" -Value $config -Encoding UTF8

Write-Host "Enrolling with the server..."
# Global options (--server, --insecure-http) must come BEFORE the subcommand;
# --token belongs to the enroll subcommand.
$enrollArgs = @("--server", $ServerUrl)
if ($allowHttp) { $enrollArgs += "--insecure-http" }
$enrollArgs += @("enroll", "--token", $EnrollToken)
& "$InstallDir\venv\Scripts\lognexa-agent.exe" @enrollArgs
if ($LASTEXITCODE -ne 0) {
  throw "Enrolment failed (exit $LASTEXITCODE). Check the server URL and that the token is valid and unused."
}

$svcName = "LognexaAgent"
$bin = "`"$InstallDir\venv\Scripts\lognexa-agent.exe`" run"
if (Get-Service $svcName -ErrorAction SilentlyContinue) { sc.exe delete $svcName | Out-Null; Start-Sleep 2 }
sc.exe create $svcName binPath= $bin start= auto DisplayName= "Lognexa Endpoint Agent" | Out-Null
sc.exe description $svcName "Collects endpoint security telemetry for Lognexa." | Out-Null
sc.exe failure $svcName reset= 86400 actions= restart/10000/restart/10000/restart/30000 | Out-Null
Start-Service $svcName
Write-Host "Lognexa agent installed and started. Check: Get-Service $svcName"
