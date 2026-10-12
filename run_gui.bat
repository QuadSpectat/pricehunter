@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m streamlit run pricehunter\gui.py --browser.gatherUsageStats false
pause
