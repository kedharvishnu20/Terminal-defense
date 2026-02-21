@echo off
title Security Monitor
echo ================================================
echo       Security Monitor — FastAPI Server
echo ================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)

echo Installing dependencies...
pip install -r "%~dp0requirements.txt" --quiet
echo.

echo Starting server at http://localhost:8000
echo Press Ctrl+C to stop.
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
