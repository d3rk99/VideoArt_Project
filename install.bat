@echo off
setlocal

if not exist .venv (
    echo Creating virtual environment...
    py -3.11 -m venv .venv
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
