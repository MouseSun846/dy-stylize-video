#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频合成服务
使用FFmpeg合成图片和音频为视频
"""

import asyncio
import subprocess
import os
import shutil
import time
from pathlib import Path
from typing import List, Optional, Dict, Callable
from PIL import Image, ImageDraw, ImageFont
import json

from utils.logger import setup_logger

class VideoComposer:
    """视频合成器"""
    
    def __init__(self, config):
        self.config = config
        self.logger = setup_logger('VideoComposer')
        
        # 检查FFmpeg是否可用
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """检查FFmpeg是否可用"""
        try:
            result = subprocess.run(
                [self.config.FFMPEG_PATH, '-version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise Exception("FFmpeg不可用")
            self.logger.info("FFmpeg检查通过")
        except Exception as e:
            self.logger.error(f"FFmpeg检查失败: {str(e)}")
            raise Exception("FFmpeg不可用，请确保已安装FFmpeg并设置正确的路径")
    
    async def compose_video(
        self,
        original_image_path: str,
        generated_image_ids: List[str],
        audio_path: Optional[str],
        config: Dict,
        task_id: str,  # 添加task_id参数
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        合成视频
        
        Args:
            original_image_path: 原始图片路径
            generated_image_ids: 生成的图片ID列表
            audio_path: 音频文件路径（可选）
            config: 视频配置
            progress_callback: 进度回调函数
            
        Returns:
            合成的视频文件路径
        """
        try:
            self.logger.info("开始视频合成")
            
            # 创建任务专用工作目录（使用项目本地目录）
            temp_base = Path(self.config.STORAGE_PATH) / 'temp'
            temp_base.mkdir(parents=True, exist_ok=True)
            
            # 使用task_id作为目录名，确保每个任务有独立的工作目录
            temp_dir_name = f'task_{task_id}'
            temp_dir = temp_base / temp_dir_name
            temp_dir.mkdir(exist_ok=True)
            temp_path = Path(temp_dir)
            
            self.logger.info(f"任务 {task_id} 工作目录: {temp_path}")
            
            try:
                # 准备图片序列
                if progress_callback:
                    progress_callback(10)
                
                image_sequence = await self._prepare_image_sequence(
                    original_image_path,
                    generated_image_ids,
                    config,
                    temp_path
                )
                
                if progress_callback:
                    progress_callback(40)
                
                # 生成视频（无音频）
                video_no_audio = await self._create_video_from_images(
                    image_sequence,
                    config,
                    temp_path
                )
                
                if progress_callback:
                    progress_callback(70)
                
                # 添加音频（如果有）
                final_video = await self._add_audio_to_video(
                    video_no_audio,
                    audio_path,
                    config,
                    temp_path
                )
                
                if progress_callback:
                    progress_callback(90)
                
                # 移动到最终位置
                output_path = Path(self.config.STORAGE_PATH) / 'videos' / f"stylized_video_{int(time.time())}.mp4"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(final_video), str(output_path))
                
                if progress_callback:
                    progress_callback(100)
                
                self.logger.info(f"视频合成完成: {output_path}")
                return str(output_path)
                
            finally:
                # 暂时不清理临时文件，便于调试
                self.logger.info(f"保留临时目录用于调试: {temp_dir}")
                # try:
                #     shutil.rmtree(str(temp_dir))
                #     self.logger.debug(f"清理临时目录: {temp_dir}")
                # except Exception as cleanup_error:
                #     self.logger.warning(f"清理临时目录失败: {cleanup_error}")
                    
        except Exception as e:
            self.logger.error(f"视频合成失败: {str(e)}")
            raise
    
    async def _prepare_image_sequence(
        self,
        original_image_path: str,
        generated_image_ids: List[str],
        config: Dict,
        temp_path: Path
    ) -> List[str]:
        """准备图片序列"""
        from services.file_manager import FileManager
        
        file_manager = FileManager(self.config.STORAGE_PATH)
        image_sequence = []
        target_size = (config['width'], config['height'])
        
        self.logger.info(f"开始准备图片序列，原始图片: {original_image_path}")
        self.logger.info(f"生成的图片ID列表: {generated_image_ids}")
        self.logger.info(f"临时目录: {temp_path}")
        
        # 添加原始图片（如果配置要求）
        if config['include_original']:
            self.logger.info("添加原始图片到序列")
            if os.path.exists(original_image_path):
                original_resized = await self._resize_and_save_image(
                    original_image_path,
                    target_size,
                    temp_path / "frame_000.jpg"
                )
                image_sequence.append(original_resized)
                self.logger.info(f"原始图片处理完成: {original_resized}")
            else:
                self.logger.error(f"原始图片不存在: {original_image_path}")
        
        # 添加生成的图片
        for i, image_id in enumerate(generated_image_ids):
            if image_id:  # 跳过None值
                image_path = file_manager.get_file_path(image_id)
                self.logger.info(f"处理生成图片 {i+1}/{len(generated_image_ids)}: ID={image_id}, Path={image_path}")
                
                if image_path and os.path.exists(image_path):
                    frame_number = len(image_sequence)
                    output_path = temp_path / f"frame_{frame_number:03d}.jpg"
                    
                    try:
                        resized_path = await self._resize_and_save_image(
                            image_path,
                            target_size,
                            output_path
                        )
                        image_sequence.append(resized_path)
                        self.logger.info(f"图片处理成功: {image_path} -> {resized_path}")
                    except Exception as e:
                        self.logger.error(f"图片处理失败 {image_path}: {str(e)}")
                else:
                    self.logger.warning(f"图片文件不存在: {image_path} (ID: {image_id})")
            else:
                self.logger.warning(f"跳过空的图片ID: {i+1}/{len(generated_image_ids)}")
        
        if not image_sequence:
            self.logger.error("没有可用的图片进行视频合成")
            # 输出调试信息
            self.logger.error(f"原始图片存在: {os.path.exists(original_image_path) if original_image_path else False}")
            self.logger.error(f"生成图片ID数量: {len([x for x in generated_image_ids if x])}")
            
            # 如果原始图片存在，尝试强制添加它
            if original_image_path and os.path.exists(original_image_path):
                self.logger.warning("所有风格图片生成失败，使用原图制作视频")
                try:
                    original_resized = await self._resize_and_save_image(
                        original_image_path,
                        target_size,
                        temp_path / "frame_000.jpg"
                    )
                    image_sequence.append(original_resized)
                    self.logger.info(f"强制添加原始图片: {original_resized}")
                except Exception as e:
                    self.logger.error(f"处理原图失败: {str(e)}")
                    raise Exception("没有可用的图片进行视频合成")
            else:
                raise Exception("没有可用的图片进行视频合成")
        
        self.logger.info(f"准备了 {len(image_sequence)} 张图片用于视频合成")
        # 输出所有图片路径
        for i, img_path in enumerate(image_sequence):
            self.logger.info(f"序列图片 {i+1}: {img_path}")
        
        return image_sequence
    
    async def _resize_and_save_image(
        self,
        input_path: str,
        target_size: tuple,
        output_path: Path
    ) -> str:
        """调整图片大小并保存"""
        try:
            with Image.open(input_path) as img:
                # 转换为RGB
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # 计算缩放比例，保持宽高比
                img_ratio = img.width / img.height
                target_ratio = target_size[0] / target_size[1]
                
                if img_ratio > target_ratio:
                    # 图片更宽，以高度为准
                    new_height = target_size[1]
                    new_width = int(new_height * img_ratio)
                else:
                    # 图片更高，以宽度为准
                    new_width = target_size[0]
                    new_height = int(new_width / img_ratio)
                
                # 调整大小
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # 创建目标大小的画布，居中放置图片
                canvas = Image.new('RGB', target_size, (0, 0, 0))
                paste_x = (target_size[0] - new_width) // 2
                paste_y = (target_size[1] - new_height) // 2
                canvas.paste(img_resized, (paste_x, paste_y))
                
                # 保存
                output_path.parent.mkdir(parents=True, exist_ok=True)
                canvas.save(output_path, 'JPEG', quality=95)
                
                # 确保文件完全写入
                import time
                time.sleep(0.05)  # 等待50毫秒
                
                # 验证文件是否正确保存
                if not output_path.exists():
                    raise Exception(f"图片保存失败: {output_path}")
                
                file_size = output_path.stat().st_size
                if file_size == 0:
                    raise Exception(f"图片文件为空: {output_path}")
                
                self.logger.debug(f"图片保存成功: {output_path} (大小: {file_size} 字节)")
                
                return str(output_path)
                
        except Exception as e:
            self.logger.error(f"图片处理失败 {input_path}: {str(e)}")
            raise
    
    async def _create_video_from_images(
        self,
        image_sequence: List[str],
        config: Dict,
        temp_path: Path
    ) -> str:
        """从图片序列创建视频"""
        try:
            # 如果只有一张图片，使用简单模式
            if len(image_sequence) <= 1:
                return await self._create_simple_video(image_sequence, config, temp_path)
            
            # 多张图片使用转场模式
            return await self._create_video_with_transitions(image_sequence, config, temp_path)
            
        except Exception as e:
            self.logger.error(f"创建视频失败: {str(e)}")
            raise
    
    async def _create_simple_video(
        self,
        image_sequence: List[str],
        config: Dict,
        temp_path: Path
    ) -> str:
        """创建简单视频（无转场）"""
        try:
            # 创建图片列表文件
            image_list_file = temp_path / "image_list.txt"
            per_slide_seconds = config['per_slide_seconds']
            
            self.logger.info(f"创建简单视频，图片数量: {len(image_sequence)}")
            
            # 生成FFmpeg的concat文件
            with open(image_list_file, 'w', encoding='utf-8') as f:
                for i, image_path in enumerate(image_sequence):
                    # 检查图片文件是否存在
                    if not os.path.exists(image_path):
                        self.logger.error(f"图片文件不存在: {image_path}")
                        raise Exception(f"图片文件不存在: {image_path}")
                    
                    # 规范化路径，处理Windows路径问题，使用绝对路径
                    absolute_path = str(Path(image_path).absolute()).replace('\\', '/')
                    
                    f.write(f"file '{absolute_path}'\n")
                    f.write(f"duration {per_slide_seconds}\n")
                    self.logger.debug(f"添加图片: {absolute_path}, 持续时间: {per_slide_seconds}s")
                
                # 最后一张图片需要额外的file行（但不需要duration）
                if image_sequence:
                    last_absolute_path = str(Path(image_sequence[-1]).absolute()).replace('\\', '/')
                    f.write(f"file '{last_absolute_path}'\n")
            
            # 输出视频路径
            output_video = temp_path / "video_no_audio.mp4"
            
            # FFmpeg命令 - 使用concat方式
            cmd = [
                self.config.FFMPEG_PATH,
                '-f', 'concat',
                '-safe', '0',
                '-i', str(image_list_file.absolute()),
                '-r', str(config['fps']),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-colorspace', 'bt709',
                '-color_primaries', 'bt709',
                '-color_trc', 'bt709',
                '-color_range', 'tv',
                '-b:v', self.config.VIDEO_BITRATE,
                '-preset', 'medium',
                '-v', 'warning',
                '-y',
                str(output_video.absolute())
            ]
            
            return await self._execute_ffmpeg_command(cmd, output_video, temp_path, "简单视频合成")
            
        except Exception as e:
            self.logger.error(f"创建简单视频失败: {str(e)}")
            raise
    
    async def _create_video_with_transitions(
        self,
        image_sequence: List[str],
        config: Dict,
        temp_path: Path
    ) -> str:
        """创建带转场效果的视频"""
        try:
            per_slide_seconds = config['per_slide_seconds']
            transition_seconds = config['transition_seconds']
            fps = config['fps']
            
            # 转场效果列表，从配置获取或使用默认值
            default_transitions = ['slideleft', 'slideright', 'slideup', 'slidedown']
            transition_types = config.get('transition_effects', default_transitions)
            
            # 如果用户没有选择任何转场效果，使用默认值
            if not transition_types:
                transition_types = default_transitions
            
            self.logger.info(f"使用转场效果: {transition_types}")            
            
            self.logger.info(f"创建带转场效果的视频，图片数量: {len(image_sequence)}")
            self.logger.info(f"每张图片持续: {per_slide_seconds}s，转场时间: {transition_seconds}s")
            
            # 验证所有图片文件存在
            for i, image_path in enumerate(image_sequence):
                if not os.path.exists(image_path):
                    self.logger.error(f"图片文件不存在: {image_path}")
                    raise Exception(f"图片文件不存在: {image_path}")
            
            # 第一步：为每张图片创建独立的视频片段
            video_segments = []
            for i, image_path in enumerate(image_sequence):
                segment_video = temp_path / f"segment_{i:03d}.mp4"
                
                # 创建单张图片的视频片段
                cmd = [
                    self.config.FFMPEG_PATH,
                    '-loop', '1',
                    '-i', str(Path(image_path).absolute()),
                    '-t', str(per_slide_seconds),
                    '-r', str(fps),
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    '-vf', f"scale={config['width']}:{config['height']}:force_original_aspect_ratio=decrease,pad={config['width']}:{config['height']}:(ow-iw)/2:(oh-ih)/2",
                    '-preset', 'medium',
                    '-v', 'warning',
                    '-y',
                    str(segment_video.absolute())
                ]
                
                self.logger.info(f"创建视频片段 {i+1}/{len(image_sequence)}: {segment_video.name}")
                await self._execute_ffmpeg_command(cmd, segment_video, temp_path, f"视频片段{i+1}")
                video_segments.append(str(segment_video.absolute()))
            
            # 第二步：使用xfade滤镜连接所有片段
            output_video = temp_path / "video_no_audio.mp4"
            
            if len(video_segments) == 1:
                # 只有一个片段，直接复制
                shutil.copy(video_segments[0], str(output_video))
                self.logger.info("只有一个视频片段，直接使用")
            else:
                # 构建复杂的filter_complex命令
                inputs = []
                for segment in video_segments:
                    inputs.extend(['-i', segment])
                
                # 构建xfade滤镜链
                filter_parts = []
                current_label = "[0:v]"
                
                for i in range(len(video_segments) - 1):
                    transition_type = transition_types[i % len(transition_types)]
                    next_input = f"[{i+1}:v]"
                    output_label = f"[v{i}]" if i < len(video_segments) - 2 else ""
                    
                    # 计算转场开始时间：每个片段的持续时间减去转场时间
                    offset = per_slide_seconds - transition_seconds
                    
                    if i == 0:
                        filter_part = f"{current_label}{next_input}xfade=transition={transition_type}:duration={transition_seconds}:offset={offset}{output_label}"
                    else:
                        filter_part = f"{current_label}{next_input}xfade=transition={transition_type}:duration={transition_seconds}:offset={offset + i * (per_slide_seconds - transition_seconds)}{output_label}"
                    
                    filter_parts.append(filter_part)
                    current_label = f"[v{i}]" if output_label else ""
                
                filter_complex = ";".join(filter_parts)
                
                cmd = [
                    self.config.FFMPEG_PATH,
                ] + inputs + [
                    '-filter_complex', filter_complex,
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    '-colorspace', 'bt709',
                    '-color_primaries', 'bt709',
                    '-color_trc', 'bt709',
                    '-color_range', 'tv',
                    '-b:v', self.config.VIDEO_BITRATE,
                    '-preset', 'medium',
                    '-v', 'warning',
                    '-y',
                    str(output_video.absolute())
                ]
                
                self.logger.info(f"执行转场合成，filter_complex: {filter_complex}")
                await self._execute_ffmpeg_command(cmd, output_video, temp_path, "转场视频合成")
            
            return str(output_video)
            
        except Exception as e:
            self.logger.error(f"创建转场视频失败: {str(e)}")
            raise
    
    async def _execute_ffmpeg_command(
        self,
        cmd: List[str],
        output_file: Path,
        temp_path: Path,
        operation_name: str
    ) -> str:
        """执行FFmpeg命令的通用方法"""
        try:
            self.logger.info(f"开始{operation_name}...")
            self.logger.info(f"FFmpeg命令: {' '.join(cmd)}")
            
            # 执行命令 - 使用同步方式以避免 Windows 上的 asyncio 限制
            import subprocess
            
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(temp_path),
                timeout=600  # 10分钟超时（转场处理可能需要更长时间）
            )
            
            stdout = process.stdout
            stderr = process.stderr
            returncode = process.returncode
            
            # 记录输出信息
            stdout_text = stdout.decode('utf-8', errors='ignore') if stdout else ''
            stderr_text = stderr.decode('utf-8', errors='ignore') if stderr else ''
            
            self.logger.info(f"{operation_name} 返回码: {returncode}")
            if stdout_text:
                self.logger.debug(f"{operation_name} stdout: {stdout_text}")
            if stderr_text:
                self.logger.debug(f"{operation_name} stderr: {stderr_text}")
            
            # 等待文件系统同步
            import time
            time.sleep(0.2)
            
            # 检查输出文件
            if output_file.exists():
                file_size = output_file.stat().st_size
                if file_size > 0:
                    self.logger.info(f"{operation_name}成功: {output_file} (大小: {file_size} 字节)")
                    return str(output_file)
                else:
                    self.logger.error(f"{operation_name}生成的文件为空: {output_file}")
            else:
                self.logger.error(f"{operation_name}生成的文件不存在: {output_file}")
            
            # 如果文件不存在或为空，检查FFmpeg错误
            if returncode != 0:
                self.logger.error(f"{operation_name}失败 (返回码: {returncode}): {stderr_text}")
                raise Exception(f"{operation_name}失败 (返回码: {returncode}): {stderr_text}")
            
            raise Exception(f"{operation_name}: 输出文件创建失败")
            
        except subprocess.TimeoutExpired as timeout_error:
            self.logger.error(f"{operation_name}执行超时: {str(timeout_error)}")
            raise Exception(f"{operation_name}执行超时: {str(timeout_error)}")
        except Exception as e:
            self.logger.error(f"{operation_name}执行异常: {str(e)}")
            raise
    
    async def _add_audio_to_video(
        self,
        video_path: str,
        audio_path: Optional[str],
        config: Dict,
        temp_path: Path
    ) -> str:
        """为视频添加音频"""
        output_video = temp_path / "final_video.mp4"
        
        if not audio_path or not os.path.exists(audio_path):
            # 没有音频，直接复制视频
            shutil.copy2(video_path, output_video)
            self.logger.info("没有音频文件，使用原视频")
            return str(output_video)
        
        try:
            # 获取视频时长
            video_duration = await self._get_video_duration(video_path)
            
            # FFmpeg命令：合并视频和音频
            cmd = [
                self.config.FFMPEG_PATH,
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',  # 不重新编码视频
                '-c:a', 'aac',
                '-b:a', self.config.AUDIO_BITRATE,
                '-shortest',  # 以最短的流为准
                '-y',
                str(output_video)
            ]
            
            # 如果音频比视频长，循环音频
            if video_duration:
                cmd = [
                    self.config.FFMPEG_PATH,
                    '-i', video_path,
                    '-stream_loop', '-1',  # 无限循环音频
                    '-i', audio_path,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-b:a', self.config.AUDIO_BITRATE,
                    '-t', str(video_duration),  # 限制输出时长
                    '-y',
                    str(output_video)
                ]
            
            self.logger.info(f"添加音频到视频: {' '.join(cmd)}")
            
            # 使用同步 subprocess 以避免 Windows 上的 asyncio 限制
            import subprocess
            
            try:
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=300  # 5分钟超时
                )
                
                if process.returncode != 0:
                    error_msg = process.stderr.decode('utf-8', errors='ignore')
                    self.logger.error(f"FFmpeg音频添加失败: {error_msg}")
                    # 如果添加音频失败，返回原视频
                    shutil.copy2(video_path, output_video)
                    self.logger.warning("音频添加失败，返回无音频视频")
                else:
                    self.logger.info("音频添加成功")
                    
            except subprocess.TimeoutExpired:
                self.logger.error("音频添加超时")
                shutil.copy2(video_path, output_video)
                self.logger.warning("音频添加超时，返回无音频视频")
            
            return str(output_video)
            
        except Exception as e:
            self.logger.error(f"添加音频失败: {str(e)}")
            # 出错时返回原视频
            shutil.copy2(video_path, output_video)
            return str(output_video)
    
    async def _get_video_duration(self, video_path: str) -> Optional[float]:
        """获取视频时长"""
        try:
            cmd = [
                self.config.FFMPEG_PATH,
                '-i', video_path,
                '-f', 'null',
                '-'
            ]
            
            # 使用同步 subprocess 以避免 Windows 上的 asyncio 限制
            import subprocess
            
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60  # 1分钟超时
            )
            
            stderr_text = process.stderr.decode('utf-8', errors='ignore')
            
            # 从FFmpeg输出中解析时长
            import re
            duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})', stderr_text)
            if duration_match:
                hours = int(duration_match.group(1))
                minutes = int(duration_match.group(2))
                seconds = int(duration_match.group(3))
                centiseconds = int(duration_match.group(4))
                
                total_seconds = hours * 3600 + minutes * 60 + seconds + centiseconds / 100
                return total_seconds
            
            return None
            
        except subprocess.TimeoutExpired:
            self.logger.error("获取视频时长超时")
            return None
        except Exception as e:
            self.logger.error(f"获取视频时长失败: {str(e)}")
            return None