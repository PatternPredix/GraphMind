@echo off
rem Start the annotation server (Windows). Run from the repository root.
if "%PORT%"=="" set PORT=8000
cd /d "%~dp0backend"
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port %PORT%
