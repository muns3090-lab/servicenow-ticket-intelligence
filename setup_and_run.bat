@echo off
REM ===================================================================
REM  ServiceNow Ops Analyzer — Windows Quick Setup
REM  Requires Python 3.10+ (https://python.org/downloads)
REM ===================================================================

echo.
echo === ServiceNow Ops Analyzer Setup ===
echo.

REM Check for Python
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo [ERROR] Python not found. Install from https://python.org/downloads
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

python --version
echo.

REM Create virtual environment
IF NOT EXIST ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate and install
echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt -q

IF ERRORLEVEL 1 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo === Running demo analysis ===
echo.
python main.py demo --tickets 300 --format all --output demo_report

echo.
echo === Done! ===
echo   Open demo_report.html in your browser to see the report.
echo.
pause
