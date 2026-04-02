@echo off
setlocal

if not exist .venv\Scripts\activate.bat (
    echo Virtual environment not found. Run install.bat first.
    exit /b 1
)

if not exist config.yaml (
    echo config.yaml not found. Copy config.example.yaml to config.yaml and configure it.
    exit /b 1
)

call .venv\Scripts\activate.bat
set PYTHONPATH=%CD%\src
python -m installation_app.main --config config.yaml

endlocal
