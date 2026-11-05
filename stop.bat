@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1" %*
set "RIICHI_EXIT=%ERRORLEVEL%"
pause >nul
exit /b %RIICHI_EXIT%
