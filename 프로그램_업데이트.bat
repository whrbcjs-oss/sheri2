@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
echo [당사비주관공사 업데이트 2026.11.02.2]
echo 실행 중인 프로그램의 서버 창을 먼저 종료해 주세요.
echo 다음 화면에서 기존 프로그램 폴더의 start.bat을 선택합니다.
echo 기존 계정과 입력자료는 유지되며, 변경 전 프로그램 코드는 자동 백업됩니다.
pause
call find_python.bat
if errorlevel 1 goto fail
if "%~1"=="" (
  %FINANCE_PYTHON% apply_update.py
) else (
  %FINANCE_PYTHON% apply_update.py "%~1"
)
if errorlevel 1 goto fail
echo 업데이트 후 기존 폴더의 start.bat을 실행해 주세요.
pause
exit /b 0
:fail
echo 업데이트를 완료하지 못했습니다. 위 오류 메시지를 확인해 주세요.
pause
exit /b 1
