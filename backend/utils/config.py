#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件
"""
import shutil
import os
from pathlib import Path

class Config:
    """应用配置类"""
    
    def __init__(self):
        # 基础配置
        self.DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
        self.HOST = os.getenv('HOST', '0.0.0.0')
        self.PORT = int(os.getenv('PORT', 5000))
        
        # 存储配置
        self.BASE_DIR = Path(__file__).parent.parent
        self.STORAGE_PATH = self.BASE_DIR / 'storage'
        self.UPLOADS_PATH = self.STORAGE_PATH / 'uploads'
        self.GENERATED_PATH = self.STORAGE_PATH / 'generated'
        self.VIDEOS_PATH = self.STORAGE_PATH / 'videos'
        self.TEMP_PATH = self.STORAGE_PATH / 'temp'
        
        # OpenRouter 配置
        self.OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1/chat/completions'
        self.MODEL_ID = 'google/gemini-2.5-flash-image-preview:free'
        
        # 生成配置
        self.MAX_CONCURRENT_REQUESTS = 3
        self.REQUEST_DELAY_MS = 1200
        self.MAX_RETRY_429 = 3
        self.MAX_SLIDE_COUNT = 20
        
        # FFmpeg 配置
        self.FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'D:\\software\\ffmpeg-n7.1-latest-win64-gpl-7.1\\ffmpeg-n7.1-latest-win64-gpl-7.1\\bin\\ffmpeg.exe')
        self.VIDEO_BITRATE = '6M'
        self.AUDIO_BITRATE = '192k'
        
        # 文件大小限制
        self.MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
        self.MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50MB
        
        # 支持的艺术风格
        self.SUPPORTED_STYLES = [
            '哥特暗黑', 'Big-head cartoon', 'Vaporwave', 'Airbrush Art',
            'Sumi-e / Ink Wash Painting', 'Linocut / Woodcut', 'Psychedelic Art',
            'Pre-Raphaelite Brotherhood', 'Tenebrism / Chiaroscuro', 'Russian Constructivism',
            '赛博朋克', 'Art Nouveau', '80\'s Anime Grill',
            '白色的雕塑', 'Bauhaus Style', '自由发挥', '多种荧光色',
            'Jackson Pollock', 'Double Exposure', 'roy lichtenstein', 'Fauvism',
            '美式漫画', '赛璐璐动画', '浮世绘', 'Takeda Hiromitsu',
            'Flat Color', '黑白动漫线稿', '新海诚', 'JOJO奇妙冒险', '吉卜力'
        ]
        
        # 日志配置
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_FILE = self.STORAGE_PATH / 'logs' / 'app.log'
        
        # MongoDB配置
        self.MONGODB_URL = os.getenv('MONGODB_URL', 'mongodb://localhost:27017')
        self.MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'stylize_video')
        
        # MongoDB配置
        self.MONGODB_URL = os.getenv('MONGODB_URL', 'mongodb://narratoaiplus:narratoaiplus@localhost:27017')
        self.MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'stylize_video')
        self.MONGODB_COLLECTION_HISTORY = 'history_tasks'
        self.MONGODB_COLLECTION_FILES = 'file_metadata'