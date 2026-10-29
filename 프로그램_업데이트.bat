@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
echo Close the running start.bat server window before updating.
echo Existing accounts, company data and private app.py will be preserved.
pause
call find_python.bat
if errorlevel 1 goto fail
if "%~1"=="" (
  %FINANCE_PYTHON% apply_update.py
) else (
  %FINANCE_PYTHON% apply_update.py "%~1"
)
if errorlevel 1 goto fail
pause
exit /b 0
:fail
echo Update did not complete. Please share the error message above.
pause
exit /b 1
