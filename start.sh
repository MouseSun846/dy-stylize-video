#!/bin/bash

echo "🎨 Stylize Video - 启动脚本"
echo "=============================="

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，请先安装Python3"
    exit 1
fi

# 检查FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg 未安装，请先安装FFmpeg"
    echo "   Windows: 下载 https://ffmpeg.org/download.html"
    echo "   macOS: brew install ffmpeg"
    echo "   Ubuntu: sudo apt install ffmpeg"
    exit 1
fi

# 进入后端目录
cd backend

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建Python虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# 安装依赖
echo "📥 安装Python依赖..."
pip install -r requirements.txt

# 创建存储目录
echo "📁 创建存储目录..."
mkdir -p storage/{uploads,generated,videos,temp,logs}

# 启动后端服务
echo "🚀 启动后端服务..."
echo "   API地址: http://localhost:5000"
echo "   前端地址: ../frontend/index.html"
echo ""
python app.py