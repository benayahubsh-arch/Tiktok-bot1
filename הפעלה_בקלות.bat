@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate.bat
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
findstr /C:"הכנס_כאן" .env >nul
if not errorlevel 1 (
  echo פתחו את קובץ .env, הכניסו את טוקן הבוט ושמרו.
  notepad .env
  pause
  exit /b
)
py bot.py
pause
