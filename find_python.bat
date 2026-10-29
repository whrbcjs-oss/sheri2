@echo off
set "FINANCE_PYTHON="
py -3.12 -c "import sys; sys.exit(sys.version_info[:2] != (3,12))" >nul 2>&1
if not errorlevel 1 (
  set "FINANCE_PYTHON=py -3.12"
  exit /b 0
)
python -c "import sys; sys.exit(sys.version_info[:2] != (3,12))" >nul 2>&1
if not errorlevel 1 (
  set "FINANCE_PYTHON=python"
  exit /b 0
)
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -c "import sys; sys.exit(sys.version_info[:2] != (3,12))" >nul 2>&1
  if not errorlevel 1 (
    set "FINANCE_PYTHON=.venv\Scripts\python.exe"
    exit /b 0
  )
)
echo Python 3.12 was not found. The ZIP selection window cannot open yet.
echo Install Python 3.12 64-bit from https://www.python.org/downloads/windows/
echo Enable "Add python.exe to PATH" during installation, then run this file again.
exit /b 1
