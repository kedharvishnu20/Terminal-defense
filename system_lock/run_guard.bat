@echo off
title System Lock Guard
echo ================================================
echo           System Lock Guard - Launcher
echo ================================================
echo.

:: Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

:: Install dependencies
echo Installing dependencies...
pip install -r "%~dp0requirements.txt" --quiet
echo.

:: Parse arguments
if "%1"=="--test" (
    echo [TEST MODE] Keyboard will be blocked immediately!
    echo.
    python "%~dp0lock_guard.py" --test
) else if "%1"=="--status" (
    python "%~dp0lock_guard.py" --status
    pause
) else (
    echo Starting Lock Guard...
    echo To stop: Press Ctrl+C in this window
    echo.
    python "%~dp0lock_guard.py"
)

pause
