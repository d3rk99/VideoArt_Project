@echo off
setlocal

call scripts\setup_env.bat
call .venv\Scripts\activate
pytest -q
