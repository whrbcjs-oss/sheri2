@echo off
cd /d "%~dp0"
if not exist app.py (
  echo Run upgrade.bat and select your original ZIP first.
  pause
  exit /b 1
)
py -3.12 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 goto fail
.venv\Scripts\python.exe collaboration.py create-admin
pause
exit /b
:fail
echo Setup failed. Check the message above.
pause
exit /b 1
