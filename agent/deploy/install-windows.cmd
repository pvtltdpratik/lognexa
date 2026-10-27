@echo off
REM ============================================================================
REM  Lognexa endpoint agent - double-clickable installer wrapper.
REM
REM  .ps1 files open in Notepad when double-clicked (Windows blocks script
REM  execution by file association on purpose). This .cmd can be double-clicked:
REM  it self-elevates (UAC prompt) and runs install-windows.ps1 with the
REM  execution policy bypassed for this one invocation only.
REM
REM  Usage:
REM    Double-click, then answer the two prompts, OR run from a prompt:
REM      install-windows.cmd "https://host:8000" "lnx_your_token"
REM ============================================================================
setlocal

REM --- Re-launch elevated if we are not already Administrator ---------------
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privileges...
  if "%~1"=="" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  ) else (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
  )
  exit /b
)

REM --- Elevated from here. Work from this script's own folder. ---------------
cd /d "%~dp0"

set "ServerUrl=%~1"
set "EnrollToken=%~2"

if "%ServerUrl%"==""   set /p "ServerUrl=Enter the Lognexa server URL (e.g. https://host:8000): "
if "%EnrollToken%"=="" set /p "EnrollToken=Enter the enrolment token: "

if "%ServerUrl%"=="" (
  echo No server URL supplied - aborting.
  echo.
  pause
  exit /b 1
)
if "%EnrollToken%"=="" (
  echo No enrolment token supplied - aborting.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\install-windows.ps1" -ServerUrl "%ServerUrl%" -EnrollToken "%EnrollToken%"
set "rc=%errorlevel%"

echo.
if "%rc%"=="0" (
  echo Done.
) else (
  echo Installer exited with code %rc%.
)
pause
exit /b %rc%
