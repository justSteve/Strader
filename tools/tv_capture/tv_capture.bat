@echo off
cd /d "C:\Tools\ScreenCaps"
pip install -q -r requirements.txt 2>nul
python tv_capture.py
pause
