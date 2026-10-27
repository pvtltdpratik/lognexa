<#
.SYNOPSIS
  Install the Lognexa endpoint agent as a Windows service (auto-start).
.DESCRIPTION
  Creates C:\Program Files\Lognexa Agent, a virtual environment, installs the
  agent, writes the config, enrols with the supplied token and registers a
  service that restarts automatically. Run from an elevated PowerShell prompt.
.EXAMPLE
  .\install-windows.ps1 -ServerUrl "https://lognexa.example.com:8000" -EnrollToken "lnx_..."
#>
param(
  [Parameter(Mandatory = $true)][string]$ServerUrl,
  [Parameter(Mandatory = $true)][string]$EnrollToken,
  [string]$InstallDir = "$env:ProgramFiles\Lognexa Agent",
  [string]$CaBundle = ""
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
$config = @{ server_url = $ServerUrl; verify_tls = if ($CaBundle) { $CaBundle } else { $true } } | ConvertTo-Json
Set-Content -Path "$dataDir\config.json" -Value $config -Encoding UTF8

Write-Host "Enrolling with the server..."
& "$InstallDir\venv\Scripts\lognexa-agent.exe" enroll --server $ServerUrl --token $EnrollToken

$svcName = "LognexaAgent"
$bin = "`"$InstallDir\venv\Scripts\lognexa-agent.exe`" run"
if (Get-Service $svcName -ErrorAction SilentlyContinue) { sc.exe delete $svcName | Out-Null; Start-Sleep 2 }
sc.exe create $svcName binPath= $bin start= auto DisplayName= "Lognexa Endpoint Agent" | Out-Null
sc.exe description $svcName "Collects endpoint security telemetry for Lognexa." | Out-Null
sc.exe failure $svcName reset= 86400 actions= restart/10000/restart/10000/restart/30000 | Out-Null
Start-Service $svcName
Write-Host "Lognexa agent installed and started. Check: Get-Service $svcName"
