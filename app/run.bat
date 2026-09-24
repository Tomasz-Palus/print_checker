@echo off
cd /d "%~dp0"
title adChecker 0.1
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
echo [adChecker] instaluje/aktualizuje zaleznosci...
%PY% -m pip install -q -r requirements.txt
echo [adChecker] start serwera (Ctrl+C lub zamknij okno, aby zakonczyc)
%PY% server.py
pause
