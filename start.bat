@echo off
chcp 65001 >nul

echo 🎨 Stylize Video - FastAPI启动脚本
echo ====================================

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未安装，请先安装Python3
    pause
    exit /b 1
)

REM 检查FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo ❌ FFmpeg 未安装，请先安装FFmpeg
    echo    下载地址: https://ffmpeg.org/download.html
    echo    或使用 winget install FFmpeg
    pause
    exit /b 1
)

REM 进入后端目录
cd backend

REM 检查虚拟环境
if not exist "venv" (
    echo 📦 创建Python虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
echo 🔧 激活虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖
echo 📥 安装Python依赖...
pip install -r requirements.txt

REM 创建存储目录
echo 📁 创建存储目录...
if not exist "storage" mkdir storage
if not exist "storage\uploads" mkdir storage\uploads
if not exist "storage\generated" mkdir storage\generated
if not exist "storage\videos" mkdir storage\videos
if not exist "storage\temp" mkdir storage\temp
if not exist "storage\logs" mkdir storage\logs

REM 启动FastAPI服务
echo 🚀 启动FastAPI服务...
echo    API地址: http://localhost:5000
echo    API文档: http://localhost:5000/docs
echo    交互式API: http://localhost:5000/redoc
echo    前端地址: ..\frontend\index.html
echo.
python app.py

pause