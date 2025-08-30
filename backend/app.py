#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stylize Video Backend
视频风格转换后端服务
"""

import os
import uuid
import json
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Optional

from services.image_generator import ImageGenerator
from services.video_composer import VideoComposer
from services.file_manager import FileManager
from services.database import DatabaseService, init_database_service, close_database_service, get_database_service
from utils.config import Config
from utils.logger import setup_logger

# 初始化应用
app = FastAPI(
    title="Stylize Video API",
    description="视频风格转换后端服务",
    version="2.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic模型定义
class GenerateRequest(BaseModel):
    image_id: str
    api_key: str
    audio_id: Optional[str] = None
    slide_count: int = 2
    fps: int = 30
    per_slide_seconds: float = 3.0
    transition_seconds: float = 0.6
    transition_effects: Optional[List[str]] = None
    width: int = 1280
    height: int = 720
    include_original: bool = True
    concurrent_limit: int = 1
    selected_styles: List[str] = []

class RegenerateVideoRequest(BaseModel):
    task_id: str
    audio_id: Optional[str] = None
    fps: int = 30
    per_slide_seconds: float = 3.0
    transition_seconds: float = 0.6
    transition_effects: Optional[List[str]] = None
    width: int = 1280
    height: int = 720

class GenerateImagesRequest(BaseModel):
    """只生成图片的请求模型"""
    image_id: str
    api_key: str
    slide_count: int = 2
    concurrent_limit: int = 1
    selected_styles: List[str] = []

class ComposeVideoRequest(BaseModel):
    """从已有图片合成视频的请求模型"""
    task_id: str
    selected_image_ids: List[str]  # 用户选择的图片ID列表
    audio_id: Optional[str] = None
    fps: int = 30
    per_slide_seconds: float = 3.0
    transition_seconds: float = 0.6
    transition_effects: Optional[List[str]] = None
    width: int = 1280
    height: int = 720
    include_original: bool = True

class UploadResponse(BaseModel):
    success: bool
    file_id: str
    filename: str
    size: int
    url: str

class TaskResponse(BaseModel):
    success: bool
    task_id: str
    message: str
    status_url: str

class HealthResponse(BaseModel):
    status: str
    message: str
    timestamp: str

# 初始化服务
config = Config()
logger = setup_logger()
file_manager = FileManager(config.STORAGE_PATH)
image_generator = ImageGenerator(config)
video_composer = VideoComposer(config)

# 全局变量存储任务状态
active_tasks = {}
# history_tasks 现在存储在 MongoDB 中，不再使用内存变量

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("🚀 正在启动 Stylize Video Backend...")
    
    # 初始化MongoDB数据库连接
    try:
        await init_database_service(config)
        logger.info("✅ MongoDB数据库连接成功")
    except Exception as e:
        logger.warning(f"⚠️ MongoDB连接失败，将使用内存存储: {str(e)}")
    
    # 确保存储目录存在
    file_manager.ensure_directories()
    
    logger.info(f"📁 存储路径: {config.STORAGE_PATH}")
    logger.info(f"🌐 API地址: http://{config.HOST}:{config.PORT}")
    logger.info(f"📄 API文档: http://{config.HOST}:{config.PORT}/docs")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("🚫 正在关闭 Stylize Video Backend...")
    
    # 关闭MongoDB连接
    try:
        await close_database_service()
        logger.info("✅ MongoDB连接已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭MongoDB连接失败: {str(e)}")

@app.get('/api/health', response_model=HealthResponse)
async def health_check():
    """健康检查端点"""
    return HealthResponse(
        status='ok',
        message='Stylize Video Backend is running',
        timestamp=datetime.now().isoformat()
    )

@app.get('/api/config')
async def get_config():
    """获取配置信息"""
    return {
        'max_concurrent_requests': config.MAX_CONCURRENT_REQUESTS,
        'supported_styles': config.SUPPORTED_STYLES,
        'max_slide_count': config.MAX_SLIDE_COUNT,
        'supported_formats': {
            'image': ['jpg', 'jpeg', 'png', 'webp'],
            'audio': ['mp3', 'wav', 'aac'],
            'video': ['mp4', 'webm']
        }
    }

@app.get('/api/database/status')
async def get_database_status():
    """获取数据库状态"""
    db_service = await get_database_service()
    if db_service:
        stats = await db_service.get_database_stats()
        return stats
    else:
        return {"connected": False, "error": "Database service not initialized"}

@app.delete('/api/history/{task_id}')
async def delete_history_task(task_id: str):
    """删除历史任务及其相关文件"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 获取要删除的任务详情
        task = await db_service.get_history_task_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="历史任务不存在")
        
        deleted_files = []
        
        # 删除任务相关的图片文件
        if task.get('images'):
            for img in task['images']:
                if img and 'file_id' in img:
                    if file_manager.delete_file(img['file_id']):
                        deleted_files.append(f"image:{img['file_id']}")
        
        # 删除原始图片文件
        if task.get('original_image_id'):
            if file_manager.delete_file(task['original_image_id']):
                deleted_files.append(f"original:{task['original_image_id']}")
        
        # 删除视频文件
        if task.get('video_id'):
            if file_manager.delete_file(task['video_id']):
                deleted_files.append(f"video:{task['video_id']}")
        
        # 从MongoDB删除任务记录
        success = await db_service.delete_history_task(task_id)
        if not success:
            logger.warning(f"删除MongoDB记录失败，但文件已删除: {task_id}")
        
        logger.info(f"历史任务删除完成: {task_id}, 删除文件: {deleted_files}")
        
        return {
            'success': True,
            'message': f'历史任务删除成功',
            'deleted_files': deleted_files,
            'task_id': task_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除历史任务失败 (task_id: {task_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f'删除失败: {str(e)}')

@app.post('/api/database/cleanup-invalid-images')
async def cleanup_invalid_image_references():
    """清理历史任务中无效的图片引用"""
    db_service = await get_database_service()
    if not db_service or not db_service.is_connected():
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    try:
        # 获取所有历史任务
        tasks = await db_service.get_history_tasks(limit=1000)
        
        cleaned_tasks = 0
        removed_images = 0
        
        for task in tasks:
            task_id = task.get('task_id')
            images = task.get('images', [])
            
            if not images:
                continue
                
            # 检查每个图片文件是否存在
            valid_images = []
            for img in images:
                if img and 'file_id' in img:
                    file_path = file_manager.get_file_path(img['file_id'])
                    if file_path and os.path.exists(file_path):
                        valid_images.append(img)
                    else:
                        removed_images += 1
                        logger.info(f"发现无效图片引用: {img['file_id']} 在任务 {task_id} 中")
            
            # 如果有无效图片，更新任务
            if len(valid_images) != len(images):
                await db_service.history_collection.update_one(
                    {"task_id": task_id},
                    {"$set": {"images": valid_images}}
                )
                cleaned_tasks += 1
                logger.info(f"已清理任务 {task_id}，从 {len(images)} 张图片清理到 {len(valid_images)} 张")
        
        return {
            'success': True,
            'message': f'清理完成：处理了 {cleaned_tasks} 个任务，移除了 {removed_images} 个无效图片引用',
            'cleaned_tasks': cleaned_tasks,
            'removed_images': removed_images
        }
        
    except Exception as e:
        logger.error(f"清理无效图片引用失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'清理失败: {str(e)}')

@app.post('/api/upload', response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), type: str = Form(default='image')):
    """文件上传端点"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail='没有选择文件')
        
        # 验证文件类型
        if not file_manager.is_valid_file(file.filename, type):
            raise HTTPException(status_code=400, detail=f'不支持的{type}文件格式')
        
        # 检查文件大小
        file_size = 0
        content = await file.read()
        file_size = len(content)
        
        if type == 'image' and file_size > config.MAX_IMAGE_SIZE:
            raise HTTPException(status_code=413, detail='图片文件过大')
        elif type == 'audio' and file_size > config.MAX_AUDIO_SIZE:
            raise HTTPException(status_code=413, detail='音频文件过大')
        
        # 保存文件
        file_info = file_manager.save_uploaded_file_from_bytes(
            content, file.filename, type
        )
        
        return UploadResponse(
            success=True,
            file_id=file_info['file_id'],
            filename=file_info['filename'],
            size=file_info['size'],
            url=f'/api/files/{file_info["file_id"]}'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'文件上传失败: {str(e)}')

@app.post('/api/generate-images', response_model=TaskResponse)
async def generate_images_only(request: GenerateImagesRequest, background_tasks: BackgroundTasks):
    """只生成图片，不进行视频合成"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 解析配置参数
        config_params = {
            'slide_count': request.slide_count,
            'concurrent_limit': request.concurrent_limit,
            'selected_styles': request.selected_styles
        }
        
        # 初始化任务状态
        active_tasks[task_id] = {
            'status': 'started',
            'progress': 0,
            'message': '图片生成任务已开始',
            'created_at': datetime.now().isoformat(),
            'config': config_params,
            'images': [],
            'video_url': None,
            'error': None,
            'original_image_id': request.image_id,
            'generation_only': True  # 标记为只生成图片的任务
        }
        
        # 添加到后台任务
        background_tasks.add_task(
            generate_images_async,
            task_id,
            request.image_id,
            request.api_key,
            config_params
        )
        
        return TaskResponse(
            success=True,
            task_id=task_id,
            message='图片生成任务已开始',
            status_url=f'/api/tasks/{task_id}'
        )
        
    except Exception as e:
        logger.error(f"生成任务创建失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'任务创建失败: {str(e)}')

@app.post('/api/compose-video', response_model=TaskResponse)
async def compose_video_from_images(request: ComposeVideoRequest, background_tasks: BackgroundTasks):
    """从已有图片合成视频"""
    try:
        # 检查原始任务是否存在
        if request.task_id not in active_tasks:
            raise HTTPException(status_code=404, detail='原始任务不存在')
        
        original_task = active_tasks[request.task_id]
        
        # 检查原始任务是否已完成图片生成
        if not original_task.get('generation_only') or original_task.get('status') != 'images_ready':
            raise HTTPException(status_code=400, detail='原始任务不是图片生成任务或尚未完成')
        
        # 验证选中的图片ID
        available_image_ids = [img['file_id'] for img in original_task.get('images', []) if img]
        for image_id in request.selected_image_ids:
            if image_id not in available_image_ids:
                raise HTTPException(status_code=400, detail=f'无效的图片ID: {image_id}')
        
        # 生成新的任务ID
        new_task_id = str(uuid.uuid4())
        
        # 配置参数
        config_params = {
            'fps': request.fps,
            'per_slide_seconds': request.per_slide_seconds,
            'transition_seconds': request.transition_seconds,
            'transition_effects': request.transition_effects,
            'width': request.width,
            'height': request.height,
            'include_original': request.include_original
        }
        
        # 初始化新任务状态
        active_tasks[new_task_id] = {
            'status': 'started',
            'progress': 0,
            'message': '正在从选中的图片合成视频...',
            'created_at': datetime.now().isoformat(),
            'config': config_params,
            'images': [],
            'video_url': None,
            'error': None,
            'is_compose': True,
            'original_task_id': request.task_id
        }
        
        # 添加到后台任务
        background_tasks.add_task(
            compose_video_async,
            new_task_id,
            original_task['original_image_id'],
            request.audio_id,
            config_params,
            request.selected_image_ids,
            request.include_original
        )
        
        return TaskResponse(
            success=True,
            task_id=new_task_id,
            message='视频合成任务已开始',
            status_url=f'/api/tasks/{new_task_id}'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"视频合成任务创建失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'任务创建失败: {str(e)}')

@app.delete('/api/images/{image_id}')
async def delete_generated_image(image_id: str):
    """删除生成的图片"""
    try:
        # 获取图片文件路径
        image_path = file_manager.get_file_path(image_id)
        if not image_path or not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail='图片不存在')
        
        # 删除文件
        os.remove(image_path)
        
        # 从所有活跃任务中移除此图片引用
        updated_tasks = []
        for task_id, task_info in active_tasks.items():
            if 'images' in task_info:
                original_count = len(task_info['images'])
                task_info['images'] = [img for img in task_info['images'] if img and img.get('file_id') != image_id]
                if len(task_info['images']) != original_count:
                    updated_tasks.append(task_id)
        
        # 同步更新MongoDB中的历史任务
        db_service = await get_database_service()
        if db_service and db_service.is_connected():
            try:
                updated_count = await db_service.remove_image_from_history_tasks(image_id)
                logger.info(f"已从 {updated_count} 个历史任务中移除图片 {image_id}")
            except Exception as e:
                logger.error(f"更新MongoDB历史任务失败: {str(e)}")
                # 不抛出异常，因为文件已经成功删除
        
        logger.info(f"已删除图片: {image_id}，影响了 {len(updated_tasks)} 个活跃任务")
        return {'success': True, 'message': '图片删除成功'}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'删除图片失败: {str(e)}')

@app.post('/api/generate', response_model=TaskResponse)
async def generate_stylized_video(request: GenerateRequest, background_tasks: BackgroundTasks):
    """生成风格化视频的主端点"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 解析配置参数
        config_params = {
            'slide_count': request.slide_count,
            'fps': request.fps,
            'per_slide_seconds': request.per_slide_seconds,
            'transition_seconds': request.transition_seconds,
            'width': request.width,
            'height': request.height,
            'include_original': request.include_original,
            'concurrent_limit': request.concurrent_limit,
            'selected_styles': request.selected_styles
        }
        
        # 初始化任务状态
        active_tasks[task_id] = {
            'status': 'started',
            'progress': 0,
            'message': '任务已开始',
            'created_at': datetime.now().isoformat(),
            'config': config_params,
            'images': [],
            'video_url': None,
            'error': None,
            'original_image_id': request.image_id  # 保存原始图片ID
        }
        logger.info(f"任务已开始: {request.api_key}")
        # 添加到后台任务
        background_tasks.add_task(
            generate_video_async,
            task_id,
            request.image_id,
            request.api_key,
            request.audio_id,
            config_params
        )
        
        return TaskResponse(
            success=True,
            task_id=task_id,
            message='视频生成任务已开始',
            status_url=f'/api/tasks/{task_id}'
        )
        
    except Exception as e:
        logger.error(f"生成任务创建失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'任务创建失败: {str(e)}')

@app.get('/api/tasks/{task_id}')
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail='任务不存在')
    
    return active_tasks[task_id]

@app.get('/api/history')
async def get_history_tasks():
    """获取历史任务列表"""
    db_service = await get_database_service()
    
    if db_service and db_service.is_connected():
        # 从 MongoDB 获取历史任务
        try:
            tasks = await db_service.get_history_tasks(limit=100)
            
            # 转换数据格式以兼容前端
            history_list = []
            for task in tasks:
                history_list.append({
                    'task_id': task.get('task_id'),
                    'created_at': task.get('created_at'),
                    'completed_at': task.get('completed_at'),
                    'image_count': len(task.get('images', [])),
                    'config': task.get('config', {}),
                    'images': task.get('images', []),
                    'original_image_id': task.get('original_image_id'),
                    'video_url': task.get('video_url'),  # 添加视频URL字段
                    'video_id': task.get('video_id')     # 添加视频ID字段
                })
            
            logger.info(f"从 MongoDB 获取到 {len(history_list)} 个历史任务")
            return {'tasks': history_list}
            
        except Exception as e:
            logger.error(f"从 MongoDB 获取历史任务失败: {str(e)}")
            return {'tasks': [], 'error': '获取历史任务失败'}
    else:
        # MongoDB 不可用，返回空列表
        logger.warning("MongoDB 不可用，返回空历史任务列表")
        return {'tasks': [], 'warning': 'MongoDB 不可用，无法获取历史任务'}

@app.post('/api/regenerate', response_model=TaskResponse)
async def regenerate_video_from_history(request: RegenerateVideoRequest, background_tasks: BackgroundTasks):
    """从历史任务重新生成视频"""
    try:
        db_service = await get_database_service()
        history_task = None
        
        if db_service and db_service.is_connected():
            # 从 MongoDB 获取历史任务
            history_task = await db_service.get_history_task_by_id(request.task_id)
        
        if not history_task:
            raise HTTPException(status_code=404, detail='历史任务不存在')
        
        # 生成新的任务ID
        new_task_id = str(uuid.uuid4())
        
        # 配置参数
        config_params = {
            'fps': request.fps,
            'per_slide_seconds': request.per_slide_seconds,
            'transition_seconds': request.transition_seconds,
            'transition_effects': request.transition_effects,
            'width': request.width,
            'height': request.height,
            'include_original': history_task['config'].get('include_original', True)
        }
        
        # 初始化新任务状态
        active_tasks[new_task_id] = {
            'status': 'started',
            'progress': 0,
            'message': '正在从历史任务重新生成视频...',
            'created_at': datetime.now().isoformat(),
            'config': config_params,
            'images': history_task['images'],  # 复用历史图片
            'video_url': None,
            'error': None,
            'is_regenerate': True,
            'original_task_id': request.task_id
        }
        
        # 添加到后台任务
        background_tasks.add_task(
            regenerate_video_async,
            new_task_id,
            history_task['original_image_id'],
            request.audio_id,
            config_params,
            history_task['images']
        )
        
        return TaskResponse(
            success=True,
            task_id=new_task_id,
            message='视频重新生成任务已开始',
            status_url=f'/api/tasks/{new_task_id}'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新生成任务创建失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'任务创建失败: {str(e)}')

@app.get('/api/files/{file_id}')
async def serve_file(file_id: str):
    """提供文件下载服务"""
    try:
        file_path = file_manager.get_file_path(file_id)
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail='文件不存在')
        
        return FileResponse(file_path)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件服务失败: {str(e)}")
        raise HTTPException(status_code=500, detail='文件服务失败')

@app.post('/api/tasks/{task_id}/cancel')
async def cancel_task(task_id: str):
    """取消任务"""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail='任务不存在')
    
    active_tasks[task_id]['status'] = 'cancelled'
    active_tasks[task_id]['message'] = '任务已取消'
    
    return {'success': True, 'message': '任务已取消'}

async def generate_video_async(task_id: str, image_id: str, api_key: str, 
                             audio_id: Optional[str], config: Dict):
    """异步生成视频"""
    try:
        # 更新任务状态
        active_tasks[task_id]['status'] = 'processing'
        active_tasks[task_id]['message'] = '正在生成风格化图片...'
        active_tasks[task_id]['progress'] = 10
        
        # 获取原始图片路径
        image_path = file_manager.get_file_path(image_id)
        if not image_path:
            raise Exception('原始图片不存在')
        
        # 创建图片回调函数，实时保存并更新状态
        def on_image_generated(img_data):
            """When a new image is generated, save it and update task status"""
            try:
                # 保存生成的图片
                img_info = file_manager.save_generated_image(img_data, f"style_{img_data.get('index', 0)+1}")
                
                # 创建图片信息
                image_info = {
                    'index': img_data.get('index', 0) + 1,
                    'style': img_data.get('style', f'风格{img_data.get("index", 0)+1}'),
                    'url': f'/api/files/{img_info["file_id"]}',
                    'file_id': img_info['file_id']
                }
                
                # 更新任务状态，添加新图片
                if task_id in active_tasks:
                    active_tasks[task_id]['images'].append(image_info)
                    active_tasks[task_id]['message'] = f'已生成 {len(active_tasks[task_id]["images"])} 张风格化图片...'
                    
                logger.info(f"实时保存图片: {img_data.get('style', '未知风格')}")
                
            except Exception as e:
                logger.error(f"实时保存图片失败: {str(e)}")
        
        # 生成风格化图片（在线程池中执行）
        import asyncio
        loop = asyncio.get_event_loop()
        generated_images = await loop.run_in_executor(
            None, 
            lambda: image_generator.generate_stylized_images(
                image_path, api_key, config, 
                progress_callback=lambda p: update_progress(task_id, 10 + p * 0.6, '正在生成风格化图片...'),
                image_callback=on_image_generated
            )
        )
        
        # 收集已保存的图片信息（用于视频合成）
        saved_images = active_tasks[task_id]['images']
        
        # 更新进度
        active_tasks[task_id]['progress'] = 70
        active_tasks[task_id]['message'] = '正在合成视频...'
        
        # 准备视频合成
        audio_path = None
        if audio_id:
            audio_path = file_manager.get_file_path(audio_id)
            logger.info(f"音频文件路径: {audio_path}")
        
        # 调试信息：检查传递给VideoComposer的参数
        image_file_ids = [img['file_id'] for img in saved_images if img]
        logger.info(f"传递给VideoComposer的参数:")
        logger.info(f"  - 原始图片路径: {image_path}")
        logger.info(f"  - 生成图片file_id列表: {image_file_ids}")
        logger.info(f"  - 音频路径: {audio_path}")
        logger.info(f"  - 配置: {config}")
        logger.info(f"  - 已保存的图片数量: {len(saved_images)}")
        
        # 检查每个图片文件是否存在
        for img in saved_images:
            if img:
                img_path = file_manager.get_file_path(img['file_id'])
                exists = os.path.exists(img_path) if img_path else False
                logger.info(f"  图片 {img['file_id']}: {img_path} (存在: {exists})")
        
        # 合成视频
        video_path = await video_composer.compose_video(
            image_path, 
            image_file_ids,
            audio_path,
            config,
            task_id,  # 添加task_id参数，确保每个任务有独立的工作目录
            progress_callback=lambda p: update_progress(task_id, 70 + p * 0.3, '正在合成视频...')
        )
        
        # 保存视频并获取URL
        video_info = file_manager.save_video_file(video_path)
        
        # 完成任务
        completed_task = {
            'status': 'completed',
            'progress': 100,
            'message': '视频生成完成',
            'video_url': f'/api/files/{video_info["file_id"]}',
            'video_id': video_info['file_id'],
            'completed_at': datetime.now().isoformat()
        }
        
        active_tasks[task_id].update(completed_task)
        
        # 保存到MongoDB历史任务
        await save_task_to_history(task_id)
        
    except Exception as e:
        logger.error(f"视频生成失败 (task_id: {task_id}): {str(e)}")
        active_tasks[task_id].update({
            'status': 'error',
            'message': f'生成失败: {str(e)}',
            'error': str(e)
        })

async def regenerate_video_async(task_id: str, original_image_id: str, 
                                 audio_id: Optional[str], config: Dict, 
                                 existing_images: List[Dict]):
    """从历史任务重新生成视频"""
    try:
        # 更新任务状态
        active_tasks[task_id]['status'] = 'processing'
        active_tasks[task_id]['message'] = '正在重新合成视频...'
        active_tasks[task_id]['progress'] = 30
        
        # 获取原始图片路径
        image_path = file_manager.get_file_path(original_image_id)
        if not image_path:
            raise Exception('原始图片不存在')
        
        # 准备视频合成
        audio_path = None
        if audio_id:
            audio_path = file_manager.get_file_path(audio_id)
            logger.info(f"音频文件路径: {audio_path}")
        
        active_tasks[task_id]['progress'] = 50
        active_tasks[task_id]['message'] = '正在合成视频...'
        
        # 使用现有图片合成视频
        image_file_ids = [img['file_id'] for img in existing_images if img and 'file_id' in img]
        
        logger.info(f"重新生成视频参数:")
        logger.info(f"  - 原始图片路径: {image_path}")
        logger.info(f"  - 复用图片file_id列表: {image_file_ids}")
        logger.info(f"  - 音频路径: {audio_path}")
        logger.info(f"  - 配置: {config}")
        
        # 合成视频
        video_path = await video_composer.compose_video(
            image_path, 
            image_file_ids,
            audio_path,
            config,
            task_id,
            progress_callback=lambda p: update_progress(task_id, 50 + p * 0.4, '正在合成视频...')
        )
        
        # 保存视频并获取URL
        video_info = file_manager.save_video_file(video_path)
        
        # 完成任务
        completed_task = {
            'status': 'completed',
            'progress': 100,
            'message': '视频重新生成完成',
            'video_url': f'/api/files/{video_info["file_id"]}',
            'video_id': video_info['file_id'],
            'completed_at': datetime.now().isoformat()
        }
        
        active_tasks[task_id].update(completed_task)
        
        # 保存到MongoDB历史任务
        await save_task_to_history(task_id)
        
    except Exception as e:
        logger.error(f"视频重新生成失败 (task_id: {task_id}): {str(e)}")
        active_tasks[task_id].update({
            'status': 'error',
            'message': f'重新生成失败: {str(e)}',
            'error': str(e)
        })

async def generate_images_async(task_id: str, image_id: str, api_key: str, config: Dict):
    """只生成图片，不进行视频合成"""
    try:
        # 更新任务状态
        active_tasks[task_id]['status'] = 'processing'
        active_tasks[task_id]['message'] = '正在生成风格化图片...'
        active_tasks[task_id]['progress'] = 10
        
        # 获取原始图片路径
        image_path = file_manager.get_file_path(image_id)
        if not image_path:
            raise Exception('原始图片不存在')
        
        # 创建图片回调函数，实时保存并更新状态
        def on_image_generated(img_data):
            """当生成新图片时，保存并更新任务状态"""
            try:
                # 保存生成的图片
                img_info = file_manager.save_generated_image(img_data, f"style_{img_data.get('index', 0)+1}")
                
                # 创建图片信息
                image_info = {
                    'index': img_data.get('index', 0) + 1,
                    'style': img_data.get('style', f'风格{img_data.get("index", 0)+1}'),
                    'url': f'/api/files/{img_info["file_id"]}',
                    'file_id': img_info['file_id'],
                    'selected': True  # 默认选中
                }
                
                # 更新任务状态，添加新图片
                if task_id in active_tasks:
                    active_tasks[task_id]['images'].append(image_info)
                    active_tasks[task_id]['message'] = f'已生成 {len(active_tasks[task_id]["images"])} 张风格化图片...'
                    
                logger.info(f"实时保存图片: {img_data.get('style', '未知风格')}")
                
            except Exception as e:
                logger.error(f"实时保存图片失败: {str(e)}")
        
        # 生成风格化图片（在线程池中执行）
        import asyncio
        loop = asyncio.get_event_loop()
        generated_images = await loop.run_in_executor(
            None, 
            lambda: image_generator.generate_stylized_images(
                image_path, api_key, config, 
                progress_callback=lambda p: update_progress(task_id, 10 + p * 0.8, '正在生成风格化图片...'),
                image_callback=on_image_generated
            )
        )
        
        # 完成图片生成
        completed_task = {
            'status': 'images_ready',
            'progress': 100,
            'message': f'图片生成完成，共 {len(active_tasks[task_id]["images"])} 张，请选择需要的图片进行视频合成',
            'completed_at': datetime.now().isoformat()
        }
        
        active_tasks[task_id].update(completed_task)
        
        # 保存到MongoDB历史任务（用于历史功能）
        await save_task_to_history(task_id)
        
    except Exception as e:
        logger.error(f"图片生成失败 (task_id: {task_id}): {str(e)}")
        active_tasks[task_id].update({
            'status': 'error',
            'message': f'生成失败: {str(e)}',
            'error': str(e)
        })

async def compose_video_async(task_id: str, original_image_id: str, audio_id: Optional[str], 
                              config: Dict, selected_image_ids: List[str], include_original: bool):
    """从选中的图片合成视频"""
    try:
        # 更新任务状态
        active_tasks[task_id]['status'] = 'processing'
        active_tasks[task_id]['message'] = '正在准备视频合成...'
        active_tasks[task_id]['progress'] = 20
        
        # 获取原始图片路径
        image_path = file_manager.get_file_path(original_image_id)
        if not image_path:
            raise Exception('原始图片不存在')
        
        # 准备音频路径
        audio_path = None
        if audio_id:
            audio_path = file_manager.get_file_path(audio_id)
            logger.info(f"音频文件路径: {audio_path}")
        
        active_tasks[task_id]['progress'] = 40
        active_tasks[task_id]['message'] = '正在合成视频...'
        
        logger.info(f"从选中图片合成视频参数:")
        logger.info(f"  - 原始图片路径: {image_path}")
        logger.info(f"  - 选中图片ID列表: {selected_image_ids}")
        logger.info(f"  - 音频路径: {audio_path}")
        logger.info(f"  - 配置: {config}")
        logger.info(f"  - 包含原图: {include_original}")
        
        # 合成视频
        video_path = await video_composer.compose_video(
            image_path, 
            selected_image_ids,
            audio_path,
            config,
            task_id,
            progress_callback=lambda p: update_progress(task_id, 40 + p * 0.5, '正在合成视频...')
        )
        
        # 保存视频并获取URL
        video_info = file_manager.save_video_file(video_path)
        
        # 完成任务
        completed_task = {
            'status': 'completed',
            'progress': 100,
            'message': '视频合成完成',
            'video_url': f'/api/files/{video_info["file_id"]}',
            'video_id': video_info['file_id'],
            'completed_at': datetime.now().isoformat()
        }
        
        active_tasks[task_id].update(completed_task)
        
        # 保存到MongoDB历史任务
        await save_task_to_history(task_id)
        
    except Exception as e:
        logger.error(f"视频合成失败 (task_id: {task_id}): {str(e)}")
        active_tasks[task_id].update({
            'status': 'error',
            'message': f'合成失败: {str(e)}',
            'error': str(e)
        })

def update_progress(task_id: str, progress: float, message: str):
    """更新任务进度"""
    if task_id in active_tasks:
        active_tasks[task_id]['progress'] = min(100, max(0, progress))
        active_tasks[task_id]['message'] = message

async def save_task_to_history(task_id: str):
    """保存任务到MongoDB历史记录"""
    if task_id not in active_tasks:
        return False
    
    db_service = await get_database_service()
    if db_service and db_service.is_connected():
        try:
            task_data = active_tasks[task_id].copy()
            success = await db_service.save_history_task(task_id, task_data)
            if success:
                logger.info(f"任务已保存到MongoDB历史记录: {task_id}")
            return success
        except Exception as e:
            logger.error(f"保存任务到MongoDB失败 (task_id: {task_id}): {str(e)}")
            return False
    else:
        logger.warning(f"MongoDB不可用，无法保存历史任务: {task_id}")
        return False

# 挂载静态文件（前端页面） - 在所有API路由之后
frontend_path = Path(__file__).parent.parent / 'frontend'
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="static")
    logger.info(f"静态文件挂载成功: {frontend_path}")
else:
    logger.warning(f"前端目录不存在: {frontend_path}")

# FastAPI中的错误处理由HTTPException自动处理

if __name__ == '__main__':
    import uvicorn
    
    # 确保存储目录存在
    file_manager.ensure_directories()
    
    # 启动应用
    print("🚀 Stylize Video Backend (FastAPI) 启动中...")
    print(f"📁 存储路径: {config.STORAGE_PATH}")
    print(f"🌐 API地址: http://{config.HOST}:{config.PORT}")
    print(f"📄 API文档: http://{config.HOST}:{config.PORT}/docs")
    print(f"🔍 交互式API: http://{config.HOST}:{config.PORT}/redoc")
    
    uvicorn.run(
        "app:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info" if not config.DEBUG else "debug"
    )