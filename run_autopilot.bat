@echo off
title Harry Potter Shorts 100%% Autonomous Engine
cd /d "%~dp0"

set PYTHONUNBUFFERED=1

:loop
echo [%date% %time%] Starting autonomous Shorts daemon... >> autopilot.log
"C:\Users\jisha\OneDrive\Desktop\automation_clipping\evaluation\venv311\Scripts\python.exe" -u main.py --daemon >> autopilot.log 2>&1
echo [%date% %time%] Daemon stopped or crashed. Restarting in 60 seconds... >> autopilot.log
timeout /t 60 /nobreak >nul
goto loop
