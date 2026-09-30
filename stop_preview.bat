@echo off
rem ===========================================================================
rem  Stop the e-hu Campus anti-fraud preview (the pythonw/python listening on 8501).
rem ===========================================================================
setlocal
set "PORT=8501"
set "FOUND="

for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:"TCP.*:%PORT%.*LISTENING"') do (
    echo [e-hu] stopping PID %%p ...
    taskkill /PID %%p /F >nul 2>&1
    set "FOUND=1"
)

if not defined FOUND (
    echo [e-hu] nothing is listening on port %PORT%.
) else (
    echo [e-hu] stopped.
)
ping -n 3 127.0.0.1 >nul
