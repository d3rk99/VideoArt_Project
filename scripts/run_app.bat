@echo off
setlocal

call scripts\setup_env.bat
call .venv\Scripts\activate
python -m app.main --config app\config\settings.yaml
