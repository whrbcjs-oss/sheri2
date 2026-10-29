@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Copy this repair file into the SAME folder as your existing start.bat.
  echo The existing .venv folder must also be there.
  pause
  exit /b 1
)
echo Close the running start.bat server window before continuing.
echo This repair changes a Python package only. It does not change company data or accounts.
pause
.venv\Scripts\python.exe -m pip install --no-cache-dir --force-reinstall "packaging==25.0"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip check
if errorlevel 1 goto fail
.venv\Scripts\python.exe -c "from packaging.version import Version; import altair as alt; import pandas as pd; assert str(Version('0.dev0')) == '0.dev0'; alt.Chart(pd.DataFrame({'x':[1], 'y':[2]})).mark_bar().encode(x='x:Q',y='y:Q').to_dict(); print('Chart dependency check passed.')"
if errorlevel 1 goto fail
echo.
echo Dependency repair completed. Run your existing start.bat again.
echo Do NOT run upgrade.bat or create a new administrator account.
pause
exit /b 0
:fail
echo.
echo Repair did not complete. Please share the full error message above.
pause
exit /b 1
