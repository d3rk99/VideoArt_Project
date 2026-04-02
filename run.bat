@echo off
setlocal

if not exist .venv\Scripts\activate.bat (
    echo Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

if not exist config.yaml (
    echo config.yaml not found. Copy config.example.yaml to config.yaml and configure it.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
set PYTHONPATH=%CD%\src
python -m installation_app.main --config config.yaml
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Application exited with code %EXIT_CODE%.
    echo Press any key to close this window.
    pause
)

endlocal & exit /b %EXIT_CODE%
