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
                    temp_path,
                    progress_callback=lambda p: progress_callback(40 + p * 0.3) if progress_callback else None
                )
                
                if progress_callback:
                    progress_callback(70)
                
                # 添加音频（如果有）
                final_video = await self._add_audio_to_video(
                    video_no_audio,
                    audio_path,
                    config,
                    temp_path,
                    progress_callback
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
        
        # 获取循环倍数，默认1倍
        image_multiplier = config.get('image_multiplier', 1)
        self.logger.info(f"图片循环倍数: {image_multiplier}")
        
        # 首先处理原始图片（如果配置要求）
        base_images = []
        if config['include_original']:
            self.logger.info("添加原始图片到序列")
            if os.path.exists(original_image_path):
                base_images.append(('original', original_image_path))
                self.logger.info(f"原始图片添加到基础序列: {original_image_path}")
            else:
                self.logger.error(f"原始图片不存在: {original_image_path}")
        
        # 添加生成的图片到基础序列
        for i, image_id in enumerate(generated_image_ids):
            if image_id:  # 跳过None值
                image_path = file_manager.get_file_path(image_id)
                self.logger.info(f"处理生成图片 {i+1}/{len(generated_image_ids)}: ID={image_id}, Path={image_path}")
                
                if image_path and os.path.exists(image_path):
                    base_images.append(('generated', image_path))
                    self.logger.info(f"生成图片添加到基础序列: {image_path}")
                else:
                    self.logger.warning(f"图片文件不存在: {image_path} (ID: {image_id})")
            else:
                self.logger.warning(f"跳过空的图片ID: {i+1}/{len(generated_image_ids)}")
        
        # 检查是否有基础图片
        if not base_images:
            self.logger.error("没有可用的图片进行视频合成")
            # 输出调试信息
            self.logger.error(f"原始图片存在: {os.path.exists(original_image_path) if original_image_path else False}")
            self.logger.error(f"生成图片ID数量: {len([x for x in generated_image_ids if x])}")
            
            # 如果原始图片存在，尝试强制添加它
            if original_image_path and os.path.exists(original_image_path):
                self.logger.warning("所有风格图片生成失败，使用原图制作视频")
                base_images.append(('original', original_image_path))
            else:
                raise Exception("没有可用的图片进行视频合成")
        
        self.logger.info(f"基础图片序列数量: {len(base_images)}, 需要循环 {image_multiplier} 倍")
        
        # 根据倍数循环生成最终图片序列
        frame_number = 0
        for cycle in range(image_multiplier):
            self.logger.info(f"处理第 {cycle + 1}/{image_multiplier} 轮循环")
            
            for img_type, image_path in base_images:
                output_path = temp_path / f"frame_{frame_number:03d}.jpg"
                
                try:
                    resized_path = await self._resize_and_save_image(
                        image_path,
                        target_size,
                        output_path
                    )
                    image_sequence.append(resized_path)
                    self.logger.info(f"图片处理成功 (第{cycle+1}轮-{img_type}): {image_path} -> {resized_path}")
                    frame_number += 1
                except Exception as e:
                    self.logger.error(f"图片处理失败 {image_path}: {str(e)}")
        
        # 最终检查
        if not image_sequence:
            raise Exception("图片序列处理完成后仍然为空")
        
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
        temp_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """从图片序列创建视频"""
        try:
            # 如果只有一张图片，使用简单模式
            if len(image_sequence) <= 1:
                return await self._create_simple_video(image_sequence, config, temp_path, progress_callback)
            
            # 多张图片使用转场模式
            return await self._create_video_with_transitions(image_sequence, config, temp_path, progress_callback)
            
        except Exception as e:
            self.logger.error(f"创建视频失败: {str(e)}")
            raise
    
    async def _create_simple_video(
        self,
        image_sequence: List[str],
        config: Dict,
        temp_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """创建简单视频（无转场）"""
        try:
            # 创建图片列表文件
            image_list_file = temp_path / "image_list.txt"
            per_slide_seconds = config['per_slide_seconds']
            
            self.logger.info(f"创建简单视频，图片数量: {len(image_sequence)}")
            
            if progress_callback:
                progress_callback(10)
            
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
            
            if progress_callback:
                progress_callback(30)
            
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
            
            if progress_callback:
                progress_callback(50)
            
            return await self._execute_ffmpeg_command(cmd, output_video, temp_path, "简单视频合成", progress_callback)
            
        except Exception as e:
            self.logger.error(f"创建简单视频失败: {str(e)}")
            raise
    
    async def _create_video_with_transitions(
        self,
        image_sequence: List[str],
        config: Dict,
        temp_path: Path,
        progress_callback: Optional[Callable] = None
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
            
            if progress_callback:
                progress_callback(5)
            
            # 验证所有图片文件存在
            for i, image_path in enumerate(image_sequence):
                if not os.path.exists(image_path):
                    self.logger.error(f"图片文件不存在: {image_path}")
                    raise Exception(f"图片文件不存在: {image_path}")
            
            if progress_callback:
                progress_callback(10)
            
            # 第一步：为每张图片创建独立的视频片段
            video_segments = []
            total_segments = len(image_sequence)
            
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
                
                # 计算单个片段的进度：10-60%区间
                segment_start_progress = 10 + (i * 50) // total_segments
                segment_end_progress = 10 + ((i + 1) * 50) // total_segments
                
                # 进度回调传递给单个片段
                segment_callback = None
                if progress_callback:
                    segment_callback = lambda p: progress_callback(segment_start_progress + (segment_end_progress - segment_start_progress) * p / 100)
                
                await self._execute_ffmpeg_command(cmd, segment_video, temp_path, f"视频片段{i+1}", segment_callback)
                video_segments.append(str(segment_video.absolute()))
                
                # 更新片段完成进度
                if progress_callback:
                    progress_callback(segment_end_progress)
            
            # 第二步：使用xfade滤镜连接所有片段
            output_video = temp_path / "video_no_audio.mp4"
            
            if progress_callback:
                progress_callback(65)
            
            if len(video_segments) == 1:
                # 只有一个片段，直接复制
                shutil.copy(video_segments[0], str(output_video))
                self.logger.info("只有一个视频片段，直接使用")
                if progress_callback:
                    progress_callback(95)
            else:
                # 构建复杂的filter_complex命令
                inputs = []
                for segment in video_segments:
                    inputs.extend(['-i', segment])
                
                if progress_callback:
                    progress_callback(70)
                
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
                
                if progress_callback:
                    progress_callback(75)
                
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
                
                # 转场合成阶段的进度回调：75-95%
                transition_callback = None
                if progress_callback:
                    transition_callback = lambda p: progress_callback(75 + p * 0.2)
                
                await self._execute_ffmpeg_command(cmd, output_video, temp_path, "转场视频合成", transition_callback)
            
            if progress_callback:
                progress_callback(100)
            
            return str(output_video)
            
        except Exception as e:
            self.logger.error(f"创建转场视频失败: {str(e)}")
            raise
    
    async def _execute_ffmpeg_command(
        self,
        cmd: List[str],
        output_file: Path,
        temp_path: Path,
        operation_name: str,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """执行FFmpeg命令的通用方法"""
        try:
            self.logger.info(f"开始{operation_name}...")
            self.logger.info(f"FFmpeg命令: {' '.join(cmd)}")
            
            # 初始进度
            if progress_callback:
                progress_callback(0)
            
            # 执行命令 - 使用异步方式以监控进度
            import subprocess
            import asyncio
            import re
            
            # 启动FFmpeg进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(temp_path),
                universal_newlines=True,
                bufsize=1
            )
            
            # 监控进度
            progress_pattern = re.compile(r'frame=\s*(\d+)')
            time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})')
            
            stdout_lines = []
            stderr_lines = []
            
            # 异步读取输出
            async def read_output():
                loop = asyncio.get_event_loop()
                
                def read_stderr():
                    lines = []
                    try:
                        while True:
                            line = process.stderr.readline()
                            if not line:
                                break
                            lines.append(line)
                            
                            # 解析进度信息
                            if progress_callback:
                                frame_match = progress_pattern.search(line)
                                time_match = time_pattern.search(line)
                                
                                if frame_match or time_match:
                                    # 根据不同操作类型估算进度
                                    if "视频片段" in operation_name:
                                        # 单个片段进度可以基于时间估算
                                        if time_match:
                                            hours = int(time_match.group(1))
                                            minutes = int(time_match.group(2))
                                            seconds = int(time_match.group(3))
                                            total_seconds = hours * 3600 + minutes * 60 + seconds
                                            
                                            # 根据预期时长估算进度（简单估算）
                                            estimated_duration = 10  # 假设最大10秒
                                            progress = min(90, (total_seconds / estimated_duration) * 100)
                                            progress_callback(progress)
                                    
                                    elif frame_match:
                                        frame_count = int(frame_match.group(1))
                                        # 基于帧数估算进度
                                        if frame_count > 0:
                                            # 简单的帧数进度估算
                                            estimated_frames = 300  # 假设大概300帧
                                            progress = min(90, (frame_count / estimated_frames) * 100)
                                            progress_callback(progress)
                    except Exception as e:
                        self.logger.debug(f"读取stderr时出错: {e}")
                    return lines
                
                def read_stdout():
                    lines = []
                    try:
                        while True:
                            line = process.stdout.readline()
                            if not line:
                                break
                            lines.append(line)
                    except Exception as e:
                        self.logger.debug(f"读取stdout时出错: {e}")
                    return lines
                
                # 在线程池中执行读取操作
                stderr_task = loop.run_in_executor(None, read_stderr)
                stdout_task = loop.run_in_executor(None, read_stdout)
                
                # 等待进程完成或超时
                timeout = 600  # 10分钟超时
                try:
                    await asyncio.wait_for(
                        asyncio.gather(stderr_task, stdout_task),
                        timeout=timeout
                    )
                    stderr_lines.extend(await stderr_task)
                    stdout_lines.extend(await stdout_task)
                except asyncio.TimeoutError:
                    process.kill()
                    raise subprocess.TimeoutExpired(cmd, timeout)
            
            # 执行输出读取
            await read_output()
            
            # 等待进程结束
            returncode = process.wait()
            
            # 处理输出
            stdout_text = ''.join(stdout_lines)
            stderr_text = ''.join(stderr_lines)
            
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
                    # 最终进度
                    if progress_callback:
                        progress_callback(100)
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
        temp_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """为视频添加音频"""
        output_video = temp_path / "final_video.mp4"
        
        if progress_callback:
            progress_callback(70)
        
        if not audio_path or not os.path.exists(audio_path):
            # 没有音频，直接复制视频
            shutil.copy2(video_path, output_video)
            self.logger.info("没有音频文件，使用原视频")
            if progress_callback:
                progress_callback(90)
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
            
            if progress_callback:
                progress_callback(80)
            
            try:
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=300  # 5分钟超时
                )
                
                if progress_callback:
                    progress_callback(85)
                
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
            
            if progress_callback:
                progress_callback(90)
            
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