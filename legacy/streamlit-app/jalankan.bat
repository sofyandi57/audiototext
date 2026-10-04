@echo off
setlocal
set PY="C:\Users\sofyandi.sedar\AppData\Local\Programs\Python\Python312\python.exe"

if not exist %PY% (
    echo Python 3.12 tidak ditemukan di lokasi yang diharapkan:
    echo %PY%
    echo Install Python dulu dari https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Memastikan library terpasang (langkah pertama bisa lama karena mengunduh torch)...
%PY% -m pip install --quiet -r "%~dp0requirements.txt"

echo Menjalankan aplikasi...
%PY% -m streamlit run "%~dp0app.py"
pause
