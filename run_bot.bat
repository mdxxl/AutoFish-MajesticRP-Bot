@echo off
chcp 65001 >nul
cd /d "%~dp0"

title Majestic Fishing Bot
python main.py

if %errorlevel% neq 0 (
    echo.
    echo Script ended with code %errorlevel%
    pause
)
