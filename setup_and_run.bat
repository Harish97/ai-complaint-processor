@echo off
REM ============================================================
REM  One-command setup and demo run - Windows.
REM
REM    setup_and_run.bat
REM
REM  Creates a virtual environment, installs dependencies, runs the
REM  full pipeline against the offline provider (no API key, no
REM  network, no cost), then runs the test suite.
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo ==============================================================
echo  AI Customer Complaint ^& Case Processing System - setup
echo ==============================================================
echo.

REM --- 1. Check Python ---------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    echo        Install Python 3.10 or newer from https://www.python.org/downloads/
    echo        and make sure "Add Python to PATH" is ticked during install.
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.10 or newer is required.
    python --version
    exit /b 1
)

for /f "delims=" %%v in ('python --version') do echo [1/4] Using %%v

REM --- 2. Virtual environment -------------------------------------------
if not exist .venv (
    echo [2/4] Creating virtual environment in .venv ...
    python -m venv .venv
) else (
    echo [2/4] Reusing existing .venv
)

REM --- 3. Dependencies ---------------------------------------------------
echo [3/4] Installing dependencies (about 15 seconds) ...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo ERROR: dependency installation failed.
    exit /b 1
)

REM --- 4. Run ------------------------------------------------------------
echo [4/4] Running the pipeline over .\data with the offline provider ...
echo.
.venv\Scripts\python.exe run.py --provider mock --log-level WARNING

echo.
echo ==============================================================
echo  Test suite
echo ==============================================================
.venv\Scripts\python.exe -m pytest

echo.
echo ==============================================================
echo  Done.
echo.
echo  Results are in  .\output
echo    structured_data\*.json   Task 1 - validated extraction
echo    customer_emails\*.txt    Task 2 - generated customer reply
echo    case_summaries\*.md      Task 3 - internal case note
echo    final_report.csv         consolidated, one row per document
echo    logs\run.log             full DEBUG audit trail
echo.
echo  Exit code 1 from the run above is expected: data\ contains two
echo  deliberate edge cases (an empty file and an unsupported .xlsx)
echo  that demonstrate error handling.
echo.
echo  To run against a real model:
echo    copy .env.example .env     ^&^& then add your OpenAI or Gemini key
echo    .venv\Scripts\python.exe run.py
echo.
echo  Other options:
echo    .venv\Scripts\python.exe run.py --help
echo ==============================================================

endlocal
exit /b 0
