@echo off
setlocal

set "PYTHON_BOOTSTRAP_CMD="

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_BOOTSTRAP_CMD=py -3.11"
    goto :python_ready
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_BOOTSTRAP_CMD=python"
    goto :python_ready
)

echo Python was not detected. Attempting to install Python 3.11 via winget...
where winget >nul 2>nul
if errorlevel 1 (
    echo winget is not available on this system, so Python cannot be installed automatically.
    echo Please install Python 3.11 and re-run this script.
    goto :error
)

winget install --id Python.Python.3.11 --exact --accept-package-agreements --accept-source-agreements --disable-interactivity
if errorlevel 1 goto :error

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_BOOTSTRAP_CMD=py -3.11"
    goto :python_ready
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_BOOTSTRAP_CMD=python"
    goto :python_ready
)

echo Python installation appears to have completed, but Python is still not available on PATH.
echo Please restart your terminal and re-run this script.
goto :error

:python_ready
if not exist .venv (
    echo Creating virtual environment...
    %PYTHON_BOOTSTRAP_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

call .venv\Scripts\activate.bat
if errorlevel 1 goto :error

python -m pip install --upgrade pip
if errorlevel 1 goto :error

pip install -r requirements.txt
if errorlevel 1 goto :error

python -m playwright install chromium
if errorlevel 1 goto :error

echo.
echo Installation complete.
echo Copy config.example.yaml to config.yaml and edit for your environment.
endlocal
exit /b 0

:error
echo.
echo Installation failed with code %ERRORLEVEL%.
echo Press any key to close this window.
pause
endlocal
exit /b 1
