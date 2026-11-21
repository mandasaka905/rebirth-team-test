@echo off
cd /d "%~dp0"
python -c "import pathlib,subprocess,sys; subprocess.Popen([str(pathlib.Path(sys.executable).with_name('pythonw.exe')), 'agentarts_connect.py'], creationflags=0x08000000)"
