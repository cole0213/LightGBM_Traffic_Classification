@echo off
REM ===== 연구실 트래픽 대시보드 (lab_dashboard) - 포트 5002 =====
REM 이 윈도우 PC에서 실행 (tshark + Z: 드라이브 필요)
set PYTHONIOENCODING=utf-8
set PORT=5002
cd /d "V:\nmlab\99_sgs\lab_dashboard"
"C:\Users\심규상\AppData\Local\Programs\Python\Python314\python.exe" app.py
