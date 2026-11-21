@echo off
cd /d "%~dp0"
start "" "http://127.0.0.1:51437/"
python competition_start.py --port 51437
pause
