@echo off
rem Starts Memoir on Windows. First run creates a private Python environment (needs internet once).
cd /d "%~dp0engine"
where py >nul 2>nul
if %errorlevel%==0 ( set PY=py -3 ) else ( set PY=python )
if not exist .venv (
  %PY% -m venv .venv
  if errorlevel 1 ( echo Python 3.10 or newer is required. Install it from python.org and tick "Add to PATH". & pause & exit /b 1 )
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python -m memoir_engine %*
pause
