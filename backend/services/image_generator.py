#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成服务
使用OpenRouter API生成风格化图片
"""

import requests
import concurrent.futures
import base64
import json
import random
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable
from PIL import Image
import io

from utils.logger import setup_logger

class ImageGenerator:
    """图片生成器"""
    
    def __init__(self, config):
        self.config = config
        self.logger = setup_logger('ImageGenerator')
        # 使用requests会话以复用连接
        self.session = requests.Session()
        self.session.timeout = 120  # 2分钟超时
        
    def generate_stylized_images(
        self, 
        original_image_path: str, 
        api_key: str, 
        config: Dict,
        progress_callback: Optional[Callable] = None,
        image_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        生成风格化图片
        
        Args:
            original_image_path: 原始图片路径
            api_key: OpenRouter API密钥
            config: 生成配置
            progress_callback: 进度回调函数
            
        Returns:
            生成的图片数据列表
        """
        try:
            self.logger.info(f"开始生成风格化图片，数量: {config['slide_count']}")
            
            # 读取并编码原始图片
            image_data_url = self._encode_image_to_data_url(original_image_path)
            
            # 选择风格
            selected_styles = self._select_styles(config)
            
            # 使用线程池实现并发限制，但逐个处理结果
            max_workers = min(config['concurrent_limit'], len(selected_styles))
            
            results = []
            completed_count = 0
            
            # 使用线程池逐个提交任务
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_style = {}
                for i, style in enumerate(selected_styles):
                    future = executor.submit(
                        self._generate_single_image_sync,
                        api_key, image_data_url, style, i, len(selected_styles)
                    )
                    future_to_style[future] = (i, style)
                
                # 逐个处理完成的任务
                for future in concurrent.futures.as_completed(future_to_style):
                    i, style = future_to_style[future]
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                            
                            # 实时回调，通知新图片生成
                            if image_callback:
                                image_callback(result)
                            
                            completed_count += 1
                            
                            # 更新进度
                            if progress_callback:
                                progress = (completed_count / len(selected_styles)) * 100
                                progress_callback(progress)
                            
                            self.logger.info(f"风格 '{style}' 生成成功 ({completed_count}/{len(selected_styles)})")
                        else:
                            self.logger.warning(f"风格 '{style}' 生成失败")
                            completed_count += 1
                            
                            # 更新进度（包括失败的）
                            if progress_callback:
                                progress = (completed_count / len(selected_styles)) * 100
                                progress_callback(progress)
                                
                    except Exception as e:
                        self.logger.error(f"风格 {style} 生成失败: {str(e)}")
                        completed_count += 1
                        
                        # 更新进度（包括失败的）
                        if progress_callback:
                            progress = (completed_count / len(selected_styles)) * 100
                            progress_callback(progress)
            
            self.logger.info(f"图片生成完成，成功: {len(results)}/{len(selected_styles)}")
            return results
            
        except Exception as e:
            self.logger.error(f"图片生成过程出错: {str(e)}")
            raise
    
    def _generate_single_image_sync(
        self, 
        api_key: str, 
        image_data_url: str, 
        style: str, 
        index: int,
        total: int
    ) -> Optional[Dict]:
        """生成单张风格化图片（同步版本）"""
        try:
            # 添加请求间隔（避免速率限制）
            if index > 0:
                delay = max(self.config.REQUEST_DELAY_MS / 1000.0, 2.0)  # 至少等待2秒
                time.sleep(delay)
                
            # 如果是第一个请求，也稍微等待一下
            elif index == 0:
                time.sleep(1.0)
            
            self.logger.info(f"正在生成风格: {style} ({index + 1}/{total})")
            
            # 构建 prompt
            prompt = f"保持构图不变，保持人物位置不变(非常重要！！！)，把图片变成{style}风格，注意要同时修改人物的面部为对应的风格，风格改变要非常明显。"
            
            # 调用OpenRouter API
            result_data_url = self._call_openrouter_api_sync(api_key, prompt, image_data_url)
            
            if result_data_url:
                return {
                    'style': style,
                    'data_url': result_data_url,
                    'index': index
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"生成风格 {style} 时出错: {str(e)}")
            return None
    
    def _select_styles(self, config: Dict) -> List[str]:
        """选择艺术风格"""
        selected_styles = config.get('selected_styles', [])
        slide_count = config['slide_count']
        
        if not selected_styles:
            # 如果没有指定风格，随机选择
            available_styles = self.config.SUPPORTED_STYLES.copy()
            selected_styles = random.sample(available_styles, min(slide_count, len(available_styles)))
        else:
            # 确保数量匹配
            if len(selected_styles) < slide_count:
                # 如果指定的风格不够，随机补充
                remaining_styles = [s for s in self.config.SUPPORTED_STYLES if s not in selected_styles]
                needed = slide_count - len(selected_styles)
                additional = random.sample(remaining_styles, min(needed, len(remaining_styles)))
                selected_styles.extend(additional)
            elif len(selected_styles) > slide_count:
                # 如果指定的风格太多，随机选择
                selected_styles = random.sample(selected_styles, slide_count)
        
        return selected_styles[:slide_count]
    
    def _encode_image_to_data_url(self, image_path: str) -> str:
        """将图片编码为data URL"""
        try:
            # 读取图片
            with Image.open(image_path) as img:
                # 转换为RGB（去除透明通道）
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # 限制图片大小以减少API调用开销
                max_size = (2048, 2048)
                if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # 转换为JPEG格式的字节流
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85, optimize=True)
                buffer.seek(0)
                
                # 编码为base64
                image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
                return f"data:image/jpeg;base64,{image_data}"
                
        except Exception as e:
            self.logger.error(f"图片编码失败: {str(e)}")
            raise
    

    

    
    def _extract_image_from_response(self, response_data: Dict) -> Optional[str]:
        """从API响应中提取图片数据"""
        try:
            # 方法1: 标准图片响应格式
            message = response_data.get('choices', [{}])[0].get('message', {})
            
            # 检查images字段
            images = message.get('images', [])
            if images and len(images) > 0:
                image_url = images[0].get('image_url', {}).get('url', '')
                if image_url.startswith('data:image/'):
                    return image_url
            
            # 方法2: 检查content字段
            content = message.get('content', [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        # 检查image_url
                        if 'image_url' in item:
                            url = item['image_url'].get('url', '')
                            if url.startswith('data:image/'):
                                return url
                        
                        # 检查直接的url字段
                        if 'url' in item:
                            url = item['url']
                            if isinstance(url, str) and url.startswith('data:image/'):
                                return url
                        
                        # 检查image_base64字段
                        if 'image_base64' in item:
                            return f"data:image/png;base64,{item['image_base64']}"
            
            # 方法3: 全文搜索data URL
            response_text = json.dumps(response_data)
            import re
            match = re.search(r'data:image/(?:png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=]+', response_text)
            if match:
                return match.group(0)
            
            self.logger.warning("未能从API响应中提取到图片数据")
            return None
            
        except Exception as e:
            self.logger.error(f"提取图片数据时出错: {str(e)}")
            return None
    
    def _call_openrouter_api_sync(
        self, 
        api_key: str, 
        prompt: str, 
        image_data_url: str,
        attempt: int = 0
    ) -> Optional[str]:
        """调用OpenRouter API（同步版本）"""
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': self.config.MODEL_ID,
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': prompt
                        },
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': image_data_url
                            }
                        }
                    ]
                }
            ]
        }
        
        try:
            response = self.session.post(
                self.config.OPENROUTER_BASE_URL,
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 429:
                # 处理速率限制，增加重试次数
                max_retries = 5  # 增加重试次数
                if attempt < max_retries:
                    # 指数退避 + 随机抖动 + 基础等待时间
                    base_wait = 5.0  # 基础等待时间增加到5秒
                    backoff = min(base_wait + (2 ** attempt) * 3, 30) + random.uniform(0, 2.0)
                    self.logger.warning(f"速率限制，等待 {backoff:.1f} 秒后重试... (第{attempt+1}次重试)")
                    time.sleep(backoff)
                    return self._call_openrouter_api_sync(api_key, prompt, image_data_url, attempt + 1)
                else:
                    raise Exception(f"触发速率限制，重试次数已达上限({max_retries}次)")
            
            if not response.ok:
                error_text = response.text
                raise Exception(f"OpenRouter API错误 {response.status_code}: {error_text}")
            
            data = response.json()
            return self._extract_image_from_response(data)
            
        except requests.exceptions.Timeout:
            raise Exception("API请求超时")
        except Exception as e:
            # 只对特定类型的错误进行重试
            if attempt < 2 and ("timeout" in str(e).lower() or "connection" in str(e).lower()):
                self.logger.warning(f"API调用失败，重试中: {str(e)}")
                time.sleep(2.0)  # 等待2秒再重试
                return self._call_openrouter_api_sync(api_key, prompt, image_data_url, attempt + 1)
            else:
                self.logger.error(f"API调用最终失败: {str(e)}")
                raise
    
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'session') and self.session:
            try:
                self.session.close()
            except:
                pass