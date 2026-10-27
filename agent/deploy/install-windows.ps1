<#
.SYNOPSIS
  Install the Lognexa endpoint agent to start automatically at boot.
.DESCRIPTION
  Creates C:\Program Files\Lognexa Agent, a virtual environment, installs the
  agent, writes the config, enrols with the supplied token and registers a
  "LognexaAgent" scheduled task that runs the agent as SYSTEM at startup and
  restarts it on failure. (The agent is a console program, not a Windows
  service, so it is hosted by Task Scheduler rather than the Service Control
  Manager.) Run from an elevated PowerShell prompt.
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
# state.json holds the device credential: restrict the folder to SYSTEM and
# Administrators (SIDs, so this works on any Windows display language).
icacls $dataDir /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not set permissions on $dataDir" }
# Plain HTTP is accepted only for a localhost dev server (enforced by the client).
# Enable it automatically for an http:// URL, or when -AllowHttp is passed, and
# persist it so the service (which reads config.json, not CLI flags) agrees.
$allowHttp = [bool]$AllowHttp -or ($ServerUrl -like "http://*")
$config = @{
  server_url       = $ServerUrl
  verify_tls       = if ($CaBundle) { $CaBundle } else { $true }
  insecure_http_ok = $allowHttp
  log_file         = "$dataDir\agent.log"
} | ConvertTo-Json
# Write UTF-8 *without* a BOM (Set-Content -Encoding UTF8 adds one on PowerShell 5.1).
[System.IO.File]::WriteAllText("$dataDir\config.json", $config, (New-Object System.Text.UTF8Encoding $false))

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

$taskName = "LognexaAgent"
$exe = "$InstallDir\venv\Scripts\lognexa-agent.exe"

# Clean up a service left by an older installer, and any previous task.
if (Get-Service $taskName -ErrorAction SilentlyContinue) {
  Stop-Service $taskName -ErrorAction SilentlyContinue
  sc.exe delete $taskName | Out-Null
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
  Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Write-Host "Registering startup task '$taskName'..."
$action    = New-ScheduledTaskAction -Execute $exe -Argument "run" -WorkingDirectory $dataDir
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Description "Lognexa endpoint agent: collects security telemetry." `
  -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null

Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5
$state = (Get-ScheduledTask -TaskName $taskName).State
if ($state -ne "Running") {
  throw "Task '$taskName' is '$state', not running. See $dataDir\agent.log"
}
Write-Host ""
Write-Host "Lognexa agent installed and running (starts automatically at boot)."
Write-Host "  Status : Get-ScheduledTask $taskName | Select-Object TaskName, State"
Write-Host "  Log    : $dataDir\agent.log"
Write-Host "  Stop   : Stop-ScheduledTask $taskName"
Write-Host "  Remove : Unregister-ScheduledTask $taskName -Confirm:`$false"
