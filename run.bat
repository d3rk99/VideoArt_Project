@echo off
setlocal

set "VENV_PYTHON=.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

if not exist config.yaml (
    echo config.yaml not found. Copy config.example.yaml to config.yaml and configure it.
    pause
    exit /b 1
)

echo Verifying Python dependencies...
"%VENV_PYTHON%" -c "import requests" >nul 2>nul
if errorlevel 1 (
    echo Missing dependencies detected. Installing from requirements.txt...
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%CD%\src"
"%VENV_PYTHON%" -m installation_app.main --config config.yaml
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Application exited with code %EXIT_CODE%.
    echo Press any key to close this window.
    pause
)

endlocal & exit /b %EXIT_CODE%
