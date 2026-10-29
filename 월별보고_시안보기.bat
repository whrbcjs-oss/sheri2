@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
call find_python.bat
if errorlevel 1 goto fail
if not exist ".preview-venv\Scripts\python.exe" (
  %FINANCE_PYTHON% -m venv .preview-venv
  if errorlevel 1 goto fail
)
.preview-venv\Scripts\python.exe -c "import openpyxl; assert openpyxl.__version__ == '3.1.5'" >nul 2>&1
if errorlevel 1 (
  .preview-venv\Scripts\python.exe -m pip install "openpyxl==3.1.5"
  if errorlevel 1 goto fail
)
if "%~1"=="" (
  .preview-venv\Scripts\python.exe monthly_report_preview.py
) else (
  .preview-venv\Scripts\python.exe monthly_report_preview.py "%~1"
)
if errorlevel 1 goto fail
echo.
echo Report preview is ready. Your original workbook was not changed.
pause
exit /b 0
:fail
echo.
echo Preview failed. Please share the error message above.
pause
exit /b 1
