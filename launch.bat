@echo off
cd /d "%~dp0"
if not exist venv (
    echo Setting up Continuum environment...
    python -m venv venv
    venv\Scripts\pip install -r requirements.txt --quiet
    echo Done.
)
echo Launching Project Continuum...
venv\Scripts\streamlit run app.py
pause
