@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m streamlit run multiuser_app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false
pause
