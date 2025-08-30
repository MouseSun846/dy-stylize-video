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
    image_multiplier: int = 1

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

# 图库相关模型
class GalleryGroupCreateRequest(BaseModel):
    name: str

class GalleryGroupUpdateRequest(BaseModel):
    name: str

class GalleryImageBatchDeleteRequest(BaseModel):
    image_ids: List[str]

class GalleryComposeVideoRequest(BaseModel):
    """从图库图片合成视频的请求模型"""
    selected_image_ids: List[str]
    audio_id: Optional[str] = None
    fps: int = 30
    per_slide_seconds: float = 3.0
    transition_seconds: float = 0.6
    transition_effects: Optional[List[str]] = None
    width: int = 1280
    height: int = 720
    image_multiplier: int = 1
    include_original: bool = False

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

@app.get('/api/history')
async def get_history_tasks(limit: int = 50, skip: int = 0):
    """获取历史任务列表"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 获取历史任务列表
        tasks = await db_service.get_history_tasks(limit, skip)
        
        # 为每个任务添加图片计数
        for task in tasks:
            if 'images' in task:
                task['image_count'] = len(task['images'])
            else:
                task['image_count'] = 0
        
        return {
            "success": True,
            "tasks": tasks
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取历史任务列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取历史任务列表失败: {str(e)}")

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
        
        # 删除任务相关的文件
        deleted_files = []
        if 'images' in task:
            for image in task['images']:
                if 'file_id' in image:
                    file_id = image['file_id']
                    if file_manager.delete_file(file_id):
                        deleted_files.append(file_id)
        
        if 'video_id' in task:
            video_id = task['video_id']
            if file_manager.delete_file(video_id):
                deleted_files.append(video_id)
        
        # 从数据库中删除任务记录
        success = await db_service.delete_history_task(task_id)
        
        if success:
            return {
                "success": True,
                "message": f"历史任务 {task_id} 删除成功",
                "deleted_files": deleted_files,
                "deleted_count": len(deleted_files)
            }
        else:
            raise HTTPException(status_code=500, detail="删除历史任务失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除历史任务失败 (task_id: {task_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除历史任务失败: {str(e)}")

# ==================== 文件上传和管理 ====================

@app.post('/api/upload', response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), type: str = Form(...)):
    """上传文件"""
    try:
        # 验证文件类型
        if type not in ['image', 'audio', 'video']:
            raise HTTPException(status_code=400, detail="不支持的文件类型")
        
        # 验证文件扩展名
        if not file_manager.is_valid_file(file.filename, type):
            raise HTTPException(status_code=400, detail=f"不支持的文件格式: {file.filename}")
        
        # 异步读取文件内容
        content = await file.read()
        
        # 保存文件
        file_info = file_manager.save_uploaded_file(content, type, file.filename)
        
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
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")

@app.get('/api/files/{file_id}')
async def get_file(file_id: str):
    """获取文件"""
    try:
        file_path = file_manager.get_file_path(file_id)
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return FileResponse(file_path)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件失败 (file_id: {file_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文件失败: {str(e)}")

@app.delete('/api/images/{image_id}')
async def delete_image(image_id: str):
    """删除图片文件"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 从所有历史任务中移除对该图片的引用
        updated_tasks_count = await db_service.remove_image_from_history_tasks(image_id)
        logger.info(f"从 {updated_tasks_count} 个历史任务中移除了图片引用")
        
        # 删除文件
        if file_manager.delete_file(image_id):
            return {"success": True, "message": "图片删除成功"}
        else:
            raise HTTPException(status_code=404, detail="图片不存在或删除失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除图片失败 (image_id: {image_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除图片失败: {str(e)}")

# ==================== 图库功能API ====================

@app.post('/api/gallery/groups')
async def create_gallery_group(request: GalleryGroupCreateRequest):
    """创建图库分组"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 生成分组ID
        group_id = str(uuid.uuid4())
        
        # 创建分组
        success = await db_service.create_gallery_group(group_id, request.name)
        
        if success:
            return {
                "success": True,
                "group_id": group_id,
                "message": "分组创建成功"
            }
        else:
            raise HTTPException(status_code=500, detail="分组创建失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建图库分组失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建图库分组失败: {str(e)}")

@app.get('/api/gallery/groups')
async def get_gallery_groups():
    """获取所有图库分组"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 获取分组列表
        groups = await db_service.get_gallery_groups()
        
        return {
            "success": True,
            "groups": groups
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图库分组失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取图库分组失败: {str(e)}")

@app.get('/api/gallery/groups/{group_id}')
async def get_gallery_group(group_id: str):
    """获取图库分组详情"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 获取分组信息
        group = await db_service.get_gallery_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        
        return {
            "success": True,
            "group": group
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图库分组详情失败 (group_id: {group_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取图库分组详情失败: {str(e)}")

@app.put('/api/gallery/groups/{group_id}')
async def update_gallery_group(group_id: str, request: GalleryGroupUpdateRequest):
    """更新图库分组"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 检查分组是否存在
        group = await db_service.get_gallery_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        
        # 更新分组
        success = await db_service.update_gallery_group(group_id, request.name)
        
        if success:
            return {
                "success": True,
                "message": "分组更新成功"
            }
        else:
            raise HTTPException(status_code=500, detail="分组更新失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新图库分组失败 (group_id: {group_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新图库分组失败: {str(e)}")

@app.delete('/api/gallery/groups/{group_id}')
async def delete_gallery_group(group_id: str):
    """删除图库分组"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 检查分组是否存在
        group = await db_service.get_gallery_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        
        # 删除分组
        success = await db_service.delete_gallery_group(group_id)
        
        if success:
            return {
                "success": True,
                "message": "分组删除成功"
            }
        else:
            raise HTTPException(status_code=500, detail="分组删除失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除图库分组失败 (group_id: {group_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除图库分组失败: {str(e)}")

@app.post('/api/gallery/upload')
async def upload_gallery_image(file: UploadFile = File(...), group_id: str = Form(...)):
    """上传图片到图库分组"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 验证文件类型
        if not file_manager.is_valid_file(file.filename, 'image'):
            raise HTTPException(status_code=400, detail=f"不支持的图片格式: {file.filename}")
        
        # 检查分组是否存在
        group = await db_service.get_gallery_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        
        # 保存图片文件
        file_info = file_manager.save_gallery_image(file, group_id)
        
        # 保存图片信息到数据库
        metadata = {
            'width': file_info.get('width', 0),
            'height': file_info.get('height', 0),
            'size': file_info.get('size', 0),
            'filename': file_info.get('filename', ''),
            'safe_filename': file_info.get('safe_filename', '')
        }
        
        success = await db_service.add_image_to_gallery_group(
            file_info['file_id'], 
            group_id, 
            file_info['filename'], 
            metadata
        )
        
        if success:
            return {
                "success": True,
                "file_id": file_info['file_id'],
                "filename": file_info['filename'],
                "size": file_info['size'],
                "url": f'/api/files/{file_info["file_id"]}'
            }
        else:
            # 如果数据库保存失败，删除已保存的文件
            file_manager.delete_file(file_info['file_id'])
            raise HTTPException(status_code=500, detail="图片信息保存失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图库图片上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"图库图片上传失败: {str(e)}")

@app.get('/api/gallery/groups/{group_id}/images')
async def get_gallery_images(group_id: str):
    """获取图库分组中的所有图片"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 检查分组是否存在
        group = await db_service.get_gallery_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        
        # 获取分组中的图片
        images = await db_service.get_images_in_gallery_group(group_id)
        
        return {
            "success": True,
            "images": images
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图库图片失败 (group_id: {group_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取图库图片失败: {str(e)}")

@app.delete('/api/gallery/images/{image_id}')
async def delete_gallery_image(image_id: str):
    """删除图库图片"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 删除数据库记录
        success = await db_service.delete_gallery_image(image_id)
        
        if success:
            # 删除文件
            file_manager.delete_file(image_id)
            
            return {
                "success": True,
                "message": "图片删除成功"
            }
        else:
            raise HTTPException(status_code=404, detail="图片不存在")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除图库图片失败 (image_id: {image_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除图库图片失败: {str(e)}")

@app.post('/api/gallery/images/batch-delete')
async def batch_delete_gallery_images(request: GalleryImageBatchDeleteRequest):
    """批量删除图库图片"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 删除数据库记录
        deleted_count = await db_service.delete_gallery_images_batch(request.image_ids)
        
        # 删除文件
        for image_id in request.image_ids:
            file_manager.delete_file(image_id)
        
        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"成功删除 {deleted_count} 张图片"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除图库图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量删除图库图片失败: {str(e)}")

@app.post('/api/gallery/compose-video')
async def compose_gallery_video(request: GalleryComposeVideoRequest, background_tasks: BackgroundTasks):
    """从图库图片合成视频"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        active_tasks[task_id] = {
            'task_id': task_id,
            'status': 'pending',
            'message': '任务已创建，等待处理...',
            'progress': 0,
            'images': [],
            'config': request.dict(),
            'created_at': datetime.now().isoformat()
        }
        
        # 在后台执行视频合成
        background_tasks.add_task(
            compose_gallery_video_async, 
            task_id, 
            request.selected_image_ids,
            request.audio_id,
            request.dict()
        )
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "视频合成任务已启动",
            "status_url": f"/api/tasks/{task_id}"
        }
        
    except Exception as e:
        logger.error(f"启动图库视频合成任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动视频合成任务失败: {str(e)}")

async def compose_gallery_video_async(task_id: str, selected_image_ids: List[str], 
                                     audio_id: Optional[str], config: Dict):
    """从图库图片异步合成视频"""
    try:
        # 更新任务状态
        active_tasks[task_id]['status'] = 'processing'
        active_tasks[task_id]['message'] = '正在准备视频合成...'
        active_tasks[task_id]['progress'] = 20
        
        # 准备音频路径
        audio_path = None
        if audio_id:
            audio_path = file_manager.get_file_path(audio_id)
            logger.info(f"音频文件路径: {audio_path}")
        
        active_tasks[task_id]['progress'] = 40
        active_tasks[task_id]['message'] = '正在合成视频...'
        
        logger.info(f"从图库图片合成视频参数:")
        logger.info(f"  - 选中图片ID列表: {selected_image_ids}")
        logger.info(f"  - 音频路径: {audio_path}")
        logger.info(f"  - 配置: {config}")
        
        # 合成视频（使用空字符串作为原始图片路径，因为图库模式不需要原始图片）
        video_path = await video_composer.compose_video(
            "",  # 图库模式不需要原始图片
            selected_image_ids,
            audio_path,
            config,
            task_id,
            progress_callback=lambda p: update_progress(task_id, 40 + p * 0.5, '正在合成视频...')
        )
        
        # 保存视频并获取URL
        video_info = file_manager.save_video_file(video_path)
        
        # 完成任务 - 添加images字段，确保历史任务包含图片信息
        # 将选中的图片ID转换为图片信息列表
        images = []
        for image_id in selected_image_ids:
            try:
                # 获取图片文件路径
                file_path = file_manager.get_file_path(image_id)
                if file_path and os.path.exists(file_path):
                    # 获取文件基本信息
                    file_stat = os.stat(file_path)
                    # 尝试从文件名中提取原始名称信息
                    filename = os.path.basename(file_path)
                    # 创建图片信息字典
                    images.append({
                        'file_id': image_id,
                        'url': f'/api/files/{image_id}',
                        'name': f'gallery_{image_id}',
                        'size': file_stat.st_size,
                        'created_at': datetime.fromtimestamp(file_stat.st_ctime).isoformat()
                    })
            except Exception as e:
                logger.warning(f"获取图片信息失败 (image_id: {image_id}): {str(e)}")
                
        completed_task = {
            'status': 'completed',
            'progress': 100,
            'message': '视频合成完成',
            'images': images,
            'video_url': f'/api/files/{video_info["file_id"]}',
            'video_id': video_info['file_id'],
            'completed_at': datetime.now().isoformat()
        }
        
        active_tasks[task_id].update(completed_task)
        
        # 保存到MongoDB历史任务
        await save_task_to_history(task_id)
        
    except Exception as e:
        logger.error(f"图库视频合成失败 (task_id: {task_id}): {str(e)}")
        active_tasks[task_id].update({
            'status': 'error',
            'message': f'合成失败: {str(e)}',
            'error': str(e)
        })

@app.get('/api/tasks/{task_id}')
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id in active_tasks:
        return active_tasks[task_id]
    else:
        # 检查是否是历史任务
        db_service = await get_database_service()
        if db_service and db_service.is_connected():
            task = await db_service.get_history_task_by_id(task_id)
            if task:
                return task
        
        raise HTTPException(status_code=404, detail="任务不存在")

@app.post('/api/generate', response_model=TaskResponse)
async def generate_video(request: GenerateRequest, background_tasks: BackgroundTasks):
    """生成视频（包括风格化图片和视频合成）"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        active_tasks[task_id] = {
            'task_id': task_id,
            'status': 'pending',
            'message': '任务已创建，等待处理...',
            'progress': 0,
            'images': [],
            'config': request.dict(),
            'created_at': datetime.now().isoformat()
        }
        
        # 在后台执行视频生成
        background_tasks.add_task(
            generate_video_async, 
            task_id, 
            request.image_id, 
            request.api_key, 
            request.audio_id,
            request.dict()
        )
        
        return TaskResponse(
            success=True,
            task_id=task_id,
            message="视频生成任务已启动",
            status_url=f"/api/tasks/{task_id}"
        )
        
    except Exception as e:
        logger.error(f"启动视频生成任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动视频生成任务失败: {str(e)}")

@app.post('/api/regenerate')
async def regenerate_video(request: RegenerateVideoRequest, background_tasks: BackgroundTasks):
    """从历史任务重新生成视频"""
    try:
        db_service = await get_database_service()
        if not db_service or not db_service.is_connected():
            raise HTTPException(status_code=503, detail="数据库不可用")
        
        # 获取历史任务
        history_task = await db_service.get_history_task_by_id(request.task_id)
        if not history_task:
            raise HTTPException(status_code=404, detail="历史任务不存在")
        
        # 生成新的任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        active_tasks[task_id] = {
            'task_id': task_id,
            'status': 'pending',
            'message': '任务已创建，等待处理...',
            'progress': 0,
            'images': history_task.get('images', []),
            'config': request.dict(),
            'created_at': datetime.now().isoformat()
        }
        
        # 获取原始图片ID
        original_image_id = history_task.get('config', {}).get('image_id')
        if not original_image_id:
            raise HTTPException(status_code=400, detail="历史任务中未找到原始图片信息")
        
        # 在后台执行视频重新生成
        background_tasks.add_task(
            regenerate_video_async, 
            task_id, 
            original_image_id,
            request.audio_id,
            request.dict(),
            history_task.get('images', [])
        )
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "视频重新生成任务已启动",
            "status_url": f"/api/tasks/{task_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动视频重新生成任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动视频重新生成任务失败: {str(e)}")

@app.post('/api/generate-images')
async def generate_images_only(request: GenerateImagesRequest, background_tasks: BackgroundTasks):
    """只生成图片，不进行视频合成"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        active_tasks[task_id] = {
            'task_id': task_id,
            'status': 'pending',
            'message': '任务已创建，等待处理...',
            'progress': 0,
            'images': [],  # 用于存储生成的图片信息
            'config': request.dict(),
            'created_at': datetime.now().isoformat()
        }
        
        # 在后台执行图片生成
        background_tasks.add_task(
            generate_images_async, 
            task_id, 
            request.image_id, 
            request.api_key,
            request.dict()
        )
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "图片生成任务已启动",
            "status_url": f"/api/tasks/{task_id}"
        }
        
    except Exception as e:
        logger.error(f"启动图片生成任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动图片生成任务失败: {str(e)}")

@app.post('/api/compose-video')
async def compose_video(request: ComposeVideoRequest, background_tasks: BackgroundTasks):
    """从已有的图片合成视频"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        active_tasks[task_id] = {
            'task_id': task_id,
            'status': 'pending',
            'message': '任务已创建，等待处理...',
            'progress': 0,
            'images': [],  # 这里不需要图片信息，因为图片已经存在
            'config': request.dict(),
            'created_at': datetime.now().isoformat()
        }
        
        # 获取原始任务信息以获取原始图片ID
        original_task = active_tasks.get(request.task_id)
        if not original_task:
            # 检查历史任务
            db_service = await get_database_service()
            if db_service and db_service.is_connected():
                history_task = await db_service.get_history_task_by_id(request.task_id)
                if history_task:
                    original_task = history_task
                else:
                    raise HTTPException(status_code=404, detail="原始任务不存在")
            else:
                raise HTTPException(status_code=404, detail="原始任务不存在")
        
        original_image_id = original_task.get('config', {}).get('image_id')
        if not original_image_id:
            raise HTTPException(status_code=400, detail="原始任务中未找到原始图片信息")
        
        # 在后台执行视频合成
        background_tasks.add_task(
            compose_video_async, 
            task_id, 
            original_image_id,
            request.audio_id,
            request.dict(),
            request.selected_image_ids,
            request.include_original
        )
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "视频合成任务已启动",
            "status_url": f"/api/tasks/{task_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动视频合成任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动视频合成任务失败: {str(e)}")

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
        active_tasks[task_id]['message'] = '正在从历史任务重新生成视频...'
        active_tasks[task_id]['progress'] = 10
        
        # 获取原始图片路径
        image_path = file_manager.get_file_path(original_image_id)
        if not image_path:
            raise Exception('原始图片不存在')
        
        # 更新进度
        active_tasks[task_id]['progress'] = 20
        active_tasks[task_id]['message'] = '正在准备音频文件...'
        
        # 准备视频合成
        audio_path = None
        if audio_id:
            audio_path = file_manager.get_file_path(audio_id)
            logger.info(f"音频文件路径: {audio_path}")
        
        active_tasks[task_id]['progress'] = 30
        active_tasks[task_id]['message'] = '正在准备图片序列...'
        
        # 使用现有图片合成视频
        image_file_ids = [img['file_id'] for img in existing_images if img and 'file_id' in img]
        
        logger.info(f"重新生成视频参数:")
        logger.info(f"  - 原始图片路径: {image_path}")
        logger.info(f"  - 复用图片file_id列表: {image_file_ids}")
        logger.info(f"  - 音频路径: {audio_path}")
        logger.info(f"  - 配置: {config}")
        
        active_tasks[task_id]['progress'] = 40
        active_tasks[task_id]['message'] = '正在开始视频合成...'
        
        # 合成视频
        video_path = await video_composer.compose_video(
            image_path, 
            image_file_ids,
            audio_path,
            config,
            task_id,
            progress_callback=lambda p: update_progress(task_id, 40 + p * 0.5, '正在重新合成视频...')
        )
        
        # 更新进度
        active_tasks[task_id]['progress'] = 90
        active_tasks[task_id]['message'] = '正在保存视频文件...'
        
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