#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件管理服务
处理文件上传、存储、检索和管理
"""

import os
import uuid
import shutil
import hashlib
import base64
import time
from pathlib import Path
from typing import Dict, Optional, List, BinaryIO
from PIL import Image
import io

from utils.logger import setup_logger

class FileManager:
    """文件管理器"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path)
        self.uploads_path = self.storage_path / 'uploads'
        self.generated_path = self.storage_path / 'generated'
        self.videos_path = self.storage_path / 'videos'
        self.temp_path = self.storage_path / 'temp'
        self.logs_path = self.storage_path / 'logs'
        
        self.logger = setup_logger('FileManager')
        
        # 文件类型配置
        self.allowed_extensions = {
            'image': {'jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif'},
            'audio': {'mp3', 'wav', 'aac', 'ogg', 'm4a'},
            'video': {'mp4', 'webm', 'avi', 'mov', 'mkv'}
        }
        
        # 文件映射（ID -> 文件路径）
        self.file_mapping = {}
        
        # 确保目录存在
        self.ensure_directories()
    
    def ensure_directories(self):
        """确保所有必要的目录存在"""
        directories = [
            self.uploads_path,
            self.generated_path,
            self.videos_path,
            self.temp_path,
            self.logs_path
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"确保目录存在: {directory}")
    
    def is_valid_file(self, filename: str, file_type: str) -> bool:
        """验证文件是否有效"""
        if not filename:
            return False
        
        # 获取文件扩展名
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        
        # 检查扩展名是否在允许列表中
        return ext in self.allowed_extensions.get(file_type, set())
    
    def save_uploaded_file_from_bytes(self, file_bytes: bytes, filename: str, file_type: str) -> Dict:
        """
        从字节数据保存上传的文件
        
        Args:
            file_bytes: 文件字节数据
            filename: 原始文件名
            file_type: 文件类型 ('image', 'audio', 'video')
            
        Returns:
            文件信息字典
        """
        try:
            # 生成唯一文件ID
            file_id = str(uuid.uuid4())
            
            # 获取原始文件名和扩展名
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            
            # 生成安全的文件名
            safe_filename = f"{file_id}.{ext}"
            
            # 确定保存路径
            save_path = self.uploads_path / safe_filename
            
            # 保存文件
            with open(save_path, 'wb') as f:
                f.write(file_bytes)
            
            # 获取文件信息
            file_size = len(file_bytes)
            
            # 如果是图片，验证并获取额外信息
            if file_type == 'image':
                image_info = self._validate_and_get_image_info(save_path)
                if not image_info:
                    save_path.unlink()  # 删除无效文件
                    raise Exception("无效的图片文件")
            
            # 记录文件映射
            self.file_mapping[file_id] = str(save_path)
            
            file_info = {
                'file_id': file_id,
                'filename': filename,
                'safe_filename': safe_filename,
                'size': file_size,
                'type': file_type,
                'path': str(save_path),
                'created_at': time.time()
            }
            
            self.logger.info(f"文件保存成功: {file_id} -> {save_path}")
            return file_info
            
        except Exception as e:
            self.logger.error(f"文件保存失败: {str(e)}")
            raise

    def save_uploaded_file(self, file, file_type: str) -> Dict:
        """
        保存上传的文件
        
        Args:
            file: FastAPI的UploadFile对象或类似的文件对象
            file_type: 文件类型 ('image', 'audio', 'video')
            
        Returns:
            文件信息字典
        """
        try:
            # 生成唯一文件ID
            file_id = str(uuid.uuid4())
            
            # 获取原始文件名和扩展名
            original_filename = getattr(file, 'filename', 'unknown')
            ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''
            
            # 生成安全的文件名
            safe_filename = f"{file_id}.{ext}"
            
            # 确定保存路径
            save_path = self.uploads_path / safe_filename
            
            # 读取文件内容并保存
            if hasattr(file, 'read'):
                # 处理类似文件的对象
                content = file.read()
                if hasattr(file, 'seek'):
                    file.seek(0)  # 重置文件指针
            elif hasattr(file, 'file'):
                # 处理FastAPI UploadFile
                content = file.file.read()
                file.file.seek(0)  # 重置文件指针
            else:
                raise Exception("不支持的文件对象类型")
            
            # 保存文件
            with open(save_path, 'wb') as f:
                f.write(content)
            
            # 获取文件信息
            file_size = len(content)
            
            # 如果是图片，验证并获取额外信息
            if file_type == 'image':
                image_info = self._validate_and_get_image_info(save_path)
                if not image_info:
                    save_path.unlink()  # 删除无效文件
                    raise Exception("无效的图片文件")
            
            # 记录文件映射
            self.file_mapping[file_id] = str(save_path)
            
            file_info = {
                'file_id': file_id,
                'filename': original_filename,
                'safe_filename': safe_filename,
                'size': file_size,
                'type': file_type,
                'path': str(save_path),
                'created_at': time.time()
            }
            
            self.logger.info(f"文件保存成功: {file_id} -> {save_path}")
            return file_info
            
        except Exception as e:
            self.logger.error(f"文件保存失败: {str(e)}")
            raise
    
    def save_generated_image(self, image_data: Dict, prefix: str = "generated") -> Dict:
        """
        保存生成的图片
        
        Args:
            image_data: 包含data_url和其他信息的字典
            prefix: 文件名前缀
            
        Returns:
            文件信息字典
        """
        try:
            # 生成唯一文件ID
            file_id = str(uuid.uuid4())
            
            # 解析data URL
            data_url = image_data.get('data_url', '')
            if not data_url.startswith('data:image/'):
                raise Exception("无效的图片数据URL")
            
            # 提取图片数据
            header, encoded = data_url.split(',', 1)
            image_bytes = base64.b64decode(encoded)
            
            # 确定文件格式
            if 'jpeg' in header or 'jpg' in header:
                ext = 'jpg'
            elif 'png' in header:
                ext = 'png'
            elif 'webp' in header:
                ext = 'webp'
            else:
                ext = 'png'  # 默认使用PNG
            
            # 生成文件名
            style = image_data.get('style', 'unknown').replace('/', '_').replace(' ', '_')
            safe_filename = f"{prefix}_{style}_{file_id}.{ext}"
            
            # 保存路径
            save_path = self.generated_path / safe_filename
            
            # 保存文件
            with open(save_path, 'wb') as f:
                f.write(image_bytes)
            
            # 验证图片
            try:
                with Image.open(save_path) as img:
                    width, height = img.size
            except Exception as e:
                save_path.unlink()  # 删除无效文件
                raise Exception(f"生成的图片无效: {str(e)}")
            
            # 记录文件映射
            self.file_mapping[file_id] = str(save_path)
            
            file_info = {
                'file_id': file_id,
                'filename': safe_filename,
                'style': image_data.get('style', ''),
                'size': save_path.stat().st_size,
                'width': width,
                'height': height,
                'type': 'image',
                'path': str(save_path),
                'created_at': time.time()
            }
            
            self.logger.info(f"生成图片保存成功: {file_id} -> {save_path}")
            return file_info
            
        except Exception as e:
            self.logger.error(f"生成图片保存失败: {str(e)}")
            raise
    
    def save_video_file(self, video_path: str) -> Dict:
        """
        保存视频文件到正式位置
        
        Args:
            video_path: 临时视频文件路径
            
        Returns:
            文件信息字典
        """
        try:
            # 生成唯一文件ID
            file_id = str(uuid.uuid4())
            
            # 生成文件名
            timestamp = int(time.time())
            safe_filename = f"stylized_video_{timestamp}_{file_id}.mp4"
            
            # 目标路径
            target_path = self.videos_path / safe_filename
            
            # 移动文件
            shutil.move(video_path, target_path)
            
            # 记录文件映射
            self.file_mapping[file_id] = str(target_path)
            
            file_info = {
                'file_id': file_id,
                'filename': safe_filename,
                'size': target_path.stat().st_size,
                'type': 'video',
                'path': str(target_path),
                'created_at': time.time()
            }
            
            self.logger.info(f"视频文件保存成功: {file_id} -> {target_path}")
            return file_info
            
        except Exception as e:
            self.logger.error(f"视频文件保存失败: {str(e)}")
            raise
    
    def get_file_path(self, file_id: str) -> Optional[str]:
        """根据文件ID获取文件路径"""
        # 首先尝试从内存映射获取
        mapped_path = self.file_mapping.get(file_id)
        if mapped_path and os.path.exists(mapped_path):
            return mapped_path
        
        # 如果内存映射没有，尝试搜索文件系统
        self.logger.debug(f"在内存映射中未找到 {file_id}，尝试搜索文件系统...")
        
        # 搜索上传文件目录
        for file_path in self.uploads_path.glob(f"{file_id}.*"):
            if file_path.is_file():
                # 更新内存映射
                self.file_mapping[file_id] = str(file_path)
                self.logger.info(f"在uploads目录中找到文件: {file_id} -> {file_path}")
                return str(file_path)
        
        # 搜索生成文件目录
        for file_path in self.generated_path.glob(f"*{file_id}.*"):
            if file_path.is_file():
                # 更新内存映射
                self.file_mapping[file_id] = str(file_path)
                self.logger.info(f"在generated目录中找到文件: {file_id} -> {file_path}")
                return str(file_path)
        
        # 搜索视频文件目录
        for file_path in self.videos_path.glob(f"*{file_id}.*"):
            if file_path.is_file():
                # 更新内存映射
                self.file_mapping[file_id] = str(file_path)
                self.logger.info(f"在videos目录中找到文件: {file_id} -> {file_path}")
                return str(file_path)
        
        self.logger.warning(f"未找到文件: {file_id}")
        return None
    
    def delete_file(self, file_id: str) -> bool:
        """删除文件"""
        try:
            file_path = self.get_file_path(file_id)
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                # 从映射中删除（如果存在）
                if file_id in self.file_mapping:
                    del self.file_mapping[file_id]
                self.logger.info(f"文件删除成功: {file_id} -> {file_path}")
                return True
            else:
                self.logger.warning(f"要删除的文件不存在: {file_id}")
                return False
        except Exception as e:
            self.logger.error(f"文件删除失败 (file_id: {file_id}): {str(e)}")
            return False
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """清理旧文件"""
        try:
            current_time = time.time()
            cutoff_time = current_time - (max_age_hours * 3600)
            
            # 清理临时文件
            self._cleanup_directory(self.temp_path, cutoff_time)
            
            # 可选：清理旧的生成文件
            # self._cleanup_directory(self.generated_path, cutoff_time)
            
            self.logger.info(f"清理完成，删除了 {max_age_hours} 小时前的临时文件")
            
        except Exception as e:
            self.logger.error(f"文件清理失败: {str(e)}")
    
    def _cleanup_directory(self, directory: Path, cutoff_time: float):
        """清理指定目录中的旧文件"""
        if not directory.exists():
            return
        
        for file_path in directory.iterdir():
            if file_path.is_file():
                try:
                    if file_path.stat().st_mtime < cutoff_time:
                        file_path.unlink()
                        self.logger.debug(f"删除旧文件: {file_path}")
                except Exception as e:
                    self.logger.error(f"删除文件失败 {file_path}: {str(e)}")
    
    def _validate_and_get_image_info(self, image_path: Path) -> Optional[Dict]:
        """验证图片并获取信息"""
        try:
            with Image.open(image_path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode
                }
        except Exception as e:
            self.logger.error(f"图片验证失败 {image_path}: {str(e)}")
            return None
    
    def get_storage_stats(self) -> Dict:
        """获取存储统计信息"""
        try:
            stats = {
                'uploads': self._get_directory_stats(self.uploads_path),
                'generated': self._get_directory_stats(self.generated_path),
                'videos': self._get_directory_stats(self.videos_path),
                'temp': self._get_directory_stats(self.temp_path),
                'total_files': len(self.file_mapping)
            }
            return stats
        except Exception as e:
            self.logger.error(f"获取存储统计失败: {str(e)}")
            return {}
    
    def _get_directory_stats(self, directory: Path) -> Dict:
        """获取目录统计信息"""
        if not directory.exists():
            return {'count': 0, 'size': 0}
        
        count = 0
        total_size = 0
        
        try:
            for file_path in directory.iterdir():
                if file_path.is_file():
                    count += 1
                    total_size += file_path.stat().st_size
        except Exception as e:
            self.logger.error(f"目录统计失败 {directory}: {str(e)}")
        
        return {
            'count': count,
            'size': total_size,
            'size_mb': round(total_size / (1024 * 1024), 2)
        }