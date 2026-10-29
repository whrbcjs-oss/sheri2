@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
call find_python.bat
if errorlevel 1 goto fail
if "%~1"=="" (
  %FINANCE_PYTHON% upgrade.py
) else (
  %FINANCE_PYTHON% upgrade.py "%~1"
)
if errorlevel 1 goto fail
echo.
echo Upgrade completed. Run setup.bat next.
pause
exit /b 0
:fail
echo.
echo Upgrade did not complete. Please share the error message above.
pause
exit /b 1
