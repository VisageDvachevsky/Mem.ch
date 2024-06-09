@echo off
chcp 65001 >nul
cd SiteFiles
start /B python server.py
start http://127.0.0.1:5000
