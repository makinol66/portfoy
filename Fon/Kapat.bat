@echo off
echo Fon Analiz Programi Kapatiliyor...
taskkill /f /im python.exe /t
taskkill /f /im cmd.exe /fi "windowtitle eq st*"
exit