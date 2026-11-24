@echo off
rem Runs tools\<this name>.py with the project's Python (cmd and PowerShell on Windows).
setlocal
set "ROOT=%~dp0.."
set "NAME=%~n0"
set "NAME=%NAME:-=_%"
set "PYTHONUTF8=1"
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" "%ROOT%\tools\%NAME%.py" %*
exit /b %ERRORLEVEL%
