@echo off
:: Dosyanın olduğu klasöre git
cd /d "%~dp0"

:: Streamlit'i Python modülü olarak çalıştır (Bu yöntem PATH hatalarını çözer)
python -m streamlit run kap_web.py

:: Eğer yukarıdaki satır hata verirse pencere kapanmasın ki görelim
pause