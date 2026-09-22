@echo off
setlocal
cd /d "%~dp0.."
echo KaliPhoneStudio AC2003 - automatic host setup + FIRST TEST
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap-first-test.ps1" -CandidateRoot "%CD%"
set "KPS_EXIT=%ERRORLEVEL%"
echo.
if not "%KPS_EXIT%"=="0" (
  echo KaliPhoneStudio FIRST TEST stopped with error %KPS_EXIT%.
  echo Nothing in this launcher authorizes flash, erase, slot changes or persistent writes.
  pause
)
exit /b %KPS_EXIT%
