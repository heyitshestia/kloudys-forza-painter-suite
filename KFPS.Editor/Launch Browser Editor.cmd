@echo off
setlocal
start "" "%~dp0..\python\pythonw.exe" -I -B "%~dp0editor.py" --browser %*
