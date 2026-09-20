@echo off
REM pull_template.bat — sync Oracle's live template to local data/template.txt
REM %~dp0 = folder of this .bat, so it works even if double-clicked from Search (CWD=C:\Windows)
scp ubuntu@80.225.225.35:/opt/dhan-telegram/data/template.txt "%~dp0data\template.txt"
echo Pulled live template to %~dp0data\template.txt
type "%~dp0data\template.txt"
