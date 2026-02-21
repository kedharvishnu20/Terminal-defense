@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
set "SEC_DIR=%PROJECT_DIR%security_monitor"
set "LOCK_DIR=%PROJECT_DIR%system_lock"
set "VENV_DIR=%PROJECT_DIR%.venv"

:: ─────────────────────────────────────────────────────────────
::  Colors & Title
:: ─────────────────────────────────────────────────────────────
title Security Suite — Command Center
color 0B

:MAIN_MENU
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │                                                          │
echo   │     🛡️  SECURITY SUITE — COMMAND CENTER                  │
echo   │     Security Monitor + System Lock Guard                 │
echo   │                                                          │
echo   └──────────────────────────────────────────────────────────┘
echo.
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo     📡  SECURITY MONITOR
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo     [1]  Start Security Monitor Server
echo     [2]  Start Monitor Only (background scanner)
echo     [3]  Open Dashboard in Browser
echo.
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo     🔒  SYSTEM LOCK GUARD
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo     [4]  Start Lock Guard (normal mode)
echo     [5]  Start Lock Guard (test mode — blocks immediately)
echo     [6]  View Lock Guard Status
echo     [7]  Edit Lock Guard Config
echo.
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo     ⚙️  SETUP ^& UTILITIES
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo     [8]  Install / Update All Dependencies
echo     [9]  View Logs (Security Monitor)
echo     [10] View Logs (Lock Guard)
echo     [11] Clear All Logs
echo     [12] Edit Security Monitor Config
echo     [13] Check Python ^& Dependencies
echo.
echo   ──────────────────────────────────────────────────────────
echo     [0]  Exit
echo   ──────────────────────────────────────────────────────────
echo.
set /p "choice=  Enter choice [0-13]: "

if "%choice%"=="1"  goto START_SERVER
if "%choice%"=="2"  goto START_MONITOR
if "%choice%"=="3"  goto OPEN_DASHBOARD
if "%choice%"=="4"  goto START_GUARD
if "%choice%"=="5"  goto TEST_GUARD
if "%choice%"=="6"  goto STATUS_GUARD
if "%choice%"=="7"  goto EDIT_GUARD_CONFIG
if "%choice%"=="8"  goto INSTALL_DEPS
if "%choice%"=="9"  goto VIEW_SEC_LOGS
if "%choice%"=="10" goto VIEW_GUARD_LOGS
if "%choice%"=="11" goto CLEAR_LOGS
if "%choice%"=="12" goto EDIT_SEC_CONFIG
if "%choice%"=="13" goto CHECK_ENV
if "%choice%"=="0"  goto EXIT

echo.
echo   [!] Invalid choice. Please try again.
timeout /t 2 >nul
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  1. START SECURITY MONITOR SERVER
:: ═══════════════════════════════════════════════════════════════
:START_SERVER
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  📡 Starting Security Monitor Server                     │
echo   │  Dashboard: http://localhost:8000                        │
echo   │  Press Ctrl+C to stop                                   │
echo   └──────────────────────────────────────────────────────────┘
echo.

:: Check Python
call :CHECK_PYTHON
if %errorlevel% neq 0 goto MAIN_MENU

:: Install deps if needed
pip show fastapi >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing Security Monitor dependencies...
    pip install -r "%SEC_DIR%\requirements.txt" --quiet
    echo.
)

:: Start the monitor in background, then the server
echo   Starting background monitor...
start /B "" python "%SEC_DIR%\monitor.py"
echo   Starting FastAPI server...
echo.

cd /d "%SEC_DIR%"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
cd /d "%PROJECT_DIR%"

echo.
echo   Server stopped.
pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  2. START MONITOR ONLY (background scanner)
:: ═══════════════════════════════════════════════════════════════
:START_MONITOR
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  🔬 Starting Background Monitor (scanner only)           │
echo   │  Logs: security_monitor/logs/                            │
echo   │  Press Ctrl+C to stop                                   │
echo   └──────────────────────────────────────────────────────────┘
echo.

call :CHECK_PYTHON
if %errorlevel% neq 0 goto MAIN_MENU

pip show psutil >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing dependencies...
    pip install -r "%SEC_DIR%\requirements.txt" --quiet
    echo.
)

python "%SEC_DIR%\monitor.py"

echo.
echo   Monitor stopped.
pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  3. OPEN DASHBOARD
:: ═══════════════════════════════════════════════════════════════
:OPEN_DASHBOARD
echo.
echo   Opening dashboard at http://localhost:8000 ...
start http://localhost:8000
timeout /t 2 >nul
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  4. START LOCK GUARD (normal)
:: ═══════════════════════════════════════════════════════════════
:START_GUARD
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  🔒 Starting System Lock Guard (normal mode)             │
echo   │  Blocks during configured time window                   │
echo   │  Press Ctrl+C to stop                                   │
echo   └──────────────────────────────────────────────────────────┘
echo.

call :CHECK_PYTHON
if %errorlevel% neq 0 goto MAIN_MENU

pip show pynput >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing Lock Guard dependencies...
    pip install -r "%LOCK_DIR%\requirements.txt" --quiet
    echo.
)

python "%LOCK_DIR%\lock_guard.py"

echo.
pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  5. START LOCK GUARD (test mode)
:: ═══════════════════════════════════════════════════════════════
:TEST_GUARD
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  🧪 Starting Lock Guard in TEST MODE                     │
echo   │  Keyboard will be blocked IMMEDIATELY!                  │
echo   │  Use bypass sequence to unlock                          │
echo   └──────────────────────────────────────────────────────────┘
echo.
echo   Are you sure? Your keyboard will be blocked.
set /p "confirm=  Type YES to confirm: "
if /i not "%confirm%"=="YES" (
    echo   Cancelled.
    timeout /t 2 >nul
    goto MAIN_MENU
)
echo.

call :CHECK_PYTHON
if %errorlevel% neq 0 goto MAIN_MENU

pip show pynput >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing Lock Guard dependencies...
    pip install -r "%LOCK_DIR%\requirements.txt" --quiet
    echo.
)

python "%LOCK_DIR%\lock_guard.py" --test

echo.
pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  6. VIEW LOCK GUARD STATUS
:: ═══════════════════════════════════════════════════════════════
:STATUS_GUARD
cls
echo.

call :CHECK_PYTHON
if %errorlevel% neq 0 goto MAIN_MENU

python "%LOCK_DIR%\lock_guard.py" --status

pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  7. EDIT LOCK GUARD CONFIG
:: ═══════════════════════════════════════════════════════════════
:EDIT_GUARD_CONFIG
echo.
if exist "%LOCK_DIR%\config.json" (
    echo   Opening Lock Guard config...
    notepad "%LOCK_DIR%\config.json"
) else (
    echo   [!] Config not found. Start Lock Guard once to generate it.
    timeout /t 3 >nul
)
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  8. INSTALL / UPDATE DEPENDENCIES
:: ═══════════════════════════════════════════════════════════════
:INSTALL_DEPS
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  📦 Installing All Dependencies                          │
echo   └──────────────────────────────────────────────────────────┘
echo.

call :CHECK_PYTHON
if %errorlevel% neq 0 goto MAIN_MENU

echo   [1/2] Security Monitor dependencies...
pip install -r "%SEC_DIR%\requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo         [!] Some packages failed to install.
) else (
    echo         Done.
)
echo.

echo   [2/2] Lock Guard dependencies...
pip install -r "%LOCK_DIR%\requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo         [!] Some packages failed to install.
) else (
    echo         Done.
)
echo.

echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   All dependencies installed successfully!
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  9. VIEW SECURITY MONITOR LOGS
:: ═══════════════════════════════════════════════════════════════
:VIEW_SEC_LOGS
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  📋 Security Monitor Logs                                │
echo   └──────────────────────────────────────────────────────────┘
echo.

set "LOG_PATH=%SEC_DIR%\logs"

if not exist "%LOG_PATH%" (
    echo   [!] No logs found. Start the monitor first.
    echo.
    pause
    goto MAIN_MENU
)

echo   Available log files:
echo   ──────────────────────────────────────────────────────────
echo.

set "idx=0"
for %%f in ("%LOG_PATH%\*.*") do (
    set /a idx+=1
    set "logfile_!idx!=%%f"
    for %%s in ("%%f") do (
        echo     [!idx!] %%~nxf   ^(%%~zs bytes^)
    )
)

if %idx%==0 (
    echo   [!] Log directory is empty.
    echo.
    pause
    goto MAIN_MENU
)

echo.
echo     [0] Back to menu
echo.
set /p "logchoice=  Open file [1-%idx%]: "

if "%logchoice%"=="0" goto MAIN_MENU

set "selected=!logfile_%logchoice%!"
if defined selected (
    notepad "!selected!"
) else (
    echo   [!] Invalid selection.
    timeout /t 2 >nul
)
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  10. VIEW LOCK GUARD LOGS
:: ═══════════════════════════════════════════════════════════════
:VIEW_GUARD_LOGS
cls
echo.
set "GLOG=%LOCK_DIR%\logs\lock_guard.log"

if exist "%GLOG%" (
    echo   ┌──────────────────────────────────────────────────────────┐
    echo   │  📋 Lock Guard Log — Last 40 lines                       │
    echo   └──────────────────────────────────────────────────────────┘
    echo.

    powershell -NoProfile -Command "Get-Content '%GLOG%' -Tail 40"

    echo.
    echo   ──────────────────────────────────────────────────────────
    echo   Full log: %GLOG%
    echo.
    echo   [1] Open full log in Notepad
    echo   [0] Back to menu
    echo.
    set /p "glchoice=  Choice: "
    if "!glchoice!"=="1" notepad "%GLOG%"
) else (
    echo   [!] No Lock Guard log found. Start it first.
)

echo.
pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  11. CLEAR ALL LOGS
:: ═══════════════════════════════════════════════════════════════
:CLEAR_LOGS
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  🗑️  Clear All Logs                                      │
echo   └──────────────────────────────────────────────────────────┘
echo.
echo   This will delete:
echo     • security_monitor/logs/*
echo     • system_lock/logs/*
echo.
set /p "delconfirm=  Are you sure? Type YES to confirm: "

if /i not "%delconfirm%"=="YES" (
    echo   Cancelled.
    timeout /t 2 >nul
    goto MAIN_MENU
)

echo.
if exist "%SEC_DIR%\logs" (
    del /q "%SEC_DIR%\logs\*" 2>nul
    echo   ✓ Security Monitor logs cleared.
) else (
    echo   - No Security Monitor logs to clear.
)

if exist "%LOCK_DIR%\logs" (
    del /q "%LOCK_DIR%\logs\*" 2>nul
    echo   ✓ Lock Guard logs cleared.
) else (
    echo   - No Lock Guard logs to clear.
)

echo.
echo   Done!
pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  12. EDIT SECURITY MONITOR CONFIG
:: ═══════════════════════════════════════════════════════════════
:EDIT_SEC_CONFIG
echo.
if exist "%SEC_DIR%\config.json" (
    echo   Opening Security Monitor config...
    notepad "%SEC_DIR%\config.json"
) else (
    echo   [!] Config not found at %SEC_DIR%\config.json
    timeout /t 3 >nul
)
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  13. CHECK PYTHON & DEPS
:: ═══════════════════════════════════════════════════════════════
:CHECK_ENV
cls
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  🔍 Environment Check                                    │
echo   └──────────────────────────────────────────────────────────┘
echo.

:: Python
echo   Python:
python --version 2>nul
if %errorlevel% neq 0 (
    echo     ❌ Python NOT found!
) else (
    echo     ✅ Installed
)
echo.

:: pip
echo   pip:
pip --version 2>nul
if %errorlevel% neq 0 (
    echo     ❌ pip NOT found!
) else (
    echo     ✅ Installed
)
echo.

:: Key packages
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Package Status:
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

for %%p in (fastapi uvicorn psutil websockets pynput meta-ai-api python-multipart) do (
    pip show %%p >nul 2>&1
    if !errorlevel! equ 0 (
        echo     ✅ %%p
    ) else (
        echo     ❌ %%p — not installed
    )
)

echo.
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
pause
goto MAIN_MENU


:: ═══════════════════════════════════════════════════════════════
::  0. EXIT
:: ═══════════════════════════════════════════════════════════════
:EXIT
cls
echo.
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo     Goodbye! Stay safe. 🛡️
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
timeout /t 2 >nul
exit /b 0


:: ═══════════════════════════════════════════════════════════════
::  HELPER: Check Python
:: ═══════════════════════════════════════════════════════════════
:CHECK_PYTHON
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   ❌ Python is not installed or not in PATH!
    echo   Download from: https://python.org
    echo.
    pause
    exit /b 1
)
exit /b 0
