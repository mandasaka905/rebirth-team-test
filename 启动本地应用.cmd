@echo off
setlocal
cd /d "%~dp0"
python -m rebirth serve --open-browser
if errorlevel 1 pause
