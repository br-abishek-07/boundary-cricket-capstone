@echo off
cd /d "%~dp0"
if not exist .venv python -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python -m streamlit run app.py --browser.gatherUsageStats false
