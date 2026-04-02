@echo off
setlocal

if not exist .venv (
    echo Creating virtual environment...
    py -3.11 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Installation complete.
echo Copy config.example.yaml to config.yaml and edit for your environment.
endlocal
