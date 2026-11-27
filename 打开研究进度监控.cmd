@echo off
setlocal
if exist "D:\Programs\conda\pythonw.exe" (
    start "" "D:\Programs\conda\pythonw.exe" "%~dp0neuroprivacy\monitor.py"
    exit /b
)
where pythonw.exe >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw.exe "%~dp0neuroprivacy\monitor.py"
    exit /b
)
echo Windows Python with Tk and psutil is required.
pause
