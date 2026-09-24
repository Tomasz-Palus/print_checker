@echo off
rem Tworzy na pulpicie skrot "adChecker" z ikona programu (uruchamia run.bat).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\adChecker.lnk');" ^
  "$s.TargetPath='%~dp0run.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0adchecker.ico,0';" ^
  "$s.Description='adChecker - przygotowanie pliku do druku'; $s.Save()"
echo Skrot adChecker jest na pulpicie.
pause
