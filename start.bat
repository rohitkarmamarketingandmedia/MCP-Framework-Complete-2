@echo off
REM ============================================
REM MCP Framework - Start Server (Windows)
REM ============================================

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    MCP Framework 3.0                         ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Activate virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Run: setup.bat
    pause
    exit /b 1
)

echo Starting server...
echo.
echo   Dashboard: http://localhost:5000
echo   API:       http://localhost:5000/api
echo   Health:    http://localhost:5000/health
echo.
echo   Press Ctrl+C to stop
echo.

python run.py
