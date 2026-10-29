@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist app.py (
  echo Run upgrade.bat first. You can also drop your original ZIP onto upgrade.bat.
  pause
  exit /b 1
)
call find_python.bat
if errorlevel 1 goto fail
if not exist ".venv\Scripts\python.exe" (
  %FINANCE_PYTHON% -m venv .venv
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 goto fail
.venv\Scripts\python.exe collaboration.py create-admin
if errorlevel 1 goto fail
pause
exit /b 0
:fail
echo Setup failed. Check the message above.
pause
exit /b 1
