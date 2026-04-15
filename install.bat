@echo off
setlocal

set "PYTHON_BOOTSTRAP_CMD="
set "VENV_PYTHON=.venv\Scripts\python.exe"

call :try_python "py -3.11"
if defined PYTHON_BOOTSTRAP_CMD goto :python_ready

call :try_python "python"
if defined PYTHON_BOOTSTRAP_CMD goto :python_ready

echo Python was not detected. Attempting to install Python 3.11 via winget...
where winget >nul 2>nul
if errorlevel 1 (
    echo winget is not available on this system, so Python cannot be installed automatically.
    echo Please install Python 3.11 and re-run this script.
    goto :error
)

winget install --id Python.Python.3.11 --exact --accept-package-agreements --accept-source-agreements --disable-interactivity
if errorlevel 1 goto :error

call :try_python "py -3.11"
if defined PYTHON_BOOTSTRAP_CMD goto :python_ready

call :try_python "python"
if defined PYTHON_BOOTSTRAP_CMD goto :python_ready

if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
    set "PYTHON_BOOTSTRAP_CMD=""%LocalAppData%\Programs\Python\Python311\python.exe"""
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

"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :error

"%VENV_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :error

"%VENV_PYTHON%" -m playwright install chromium
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

:try_python
%~1 --version >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_BOOTSTRAP_CMD=%~1"
)
exit /b 0
