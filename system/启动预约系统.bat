@echo off
chcp 65001 >nul
title 实验室换能器设备实验预约系统
color 0A

echo ======================================================================
echo             🔬 实验室换能器设备实验预约系统正在启动...
echo ======================================================================
echo.
echo  正在启动本地服务...
echo  默认端口：8000
echo.

:: 延迟1.5秒自动在默认浏览器中打开主界面
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

:: 运行 Python FastAPI 后端服务
python app.py

pause
