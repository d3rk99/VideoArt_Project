@echo off
setlocal

call scripts\setup_env.bat --no-pause
if errorlevel 1 goto :fail

call .venv\Scripts\activate
if errorlevel 1 goto :fail

python -m app.main --config app\config\settings.yaml
if errorlevel 1 goto :fail

goto :end

:fail
echo.
echo run_app.bat failed with errorlevel %errorlevel%.

:end
if /I not "%~1"=="--no-pause" pause
exit /b %errorlevel%
