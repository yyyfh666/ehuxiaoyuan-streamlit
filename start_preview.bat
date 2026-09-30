@echo off
rem ===========================================================================
rem  e-hu Campus anti-fraud preview - one-click launcher (port 8501)
rem  URL: http://localhost:8501
rem  1) double-click this file            -> start (silent) + open browser
rem  2) wscript start_preview_autostart.vbs --now   -> same thing, no window
rem  NOTE: the long streamlit command must stay on ONE line.
rem ===========================================================================
setlocal
set "APPDIR=%~dp0"
set "PORT=8501"

netstat -ano | findstr /r /c:"TCP.*:%PORT%.*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [e-hu] already running - opening browser...
    start "" "http://localhost:%PORT%/"
    exit /b 0
)

set "PYW="
for /f "delims=" %%i in ('where pythonw.exe 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW for /f "delims=" %%i in ('where python.exe 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
    echo [e-hu] ERROR: python not found in PATH.
    pause
    exit /b 1
)

cd /d "%APPDIR%"
start "" "%PYW%" -m streamlit run "app.py" --server.port %PORT% --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false --server.fileWatcherType none

for /l %%n in (1,1,45) do (
    netstat -ano | findstr /r /c:"TCP.*:%PORT%.*LISTENING" >nul 2>&1
    if not errorlevel 1 (
        start "" "http://localhost:%PORT%/"
        exit /b 0
    )
    ping -n 2 127.0.0.1 >nul
)

echo [e-hu] start timed out. Run manually: python -m streamlit run app.py
pause
exit /b 1
