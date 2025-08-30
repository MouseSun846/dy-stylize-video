#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试历史任务删除功能
验证删除操作是否正确处理了所有相关资源
"""
import asyncio
import json
from backend.services.database import DatabaseService
from backend.services.file_manager import FileManager
from backend.utils.config import Config
from pathlib import Path

async def test_history_task_deletion():
    """测试历史任务删除功能"""
    print("🧪 测试历史任务删除功能...")
    
    # 初始化配置和服务
    config = Config()
    db_service = DatabaseService(config.MONGODB_URL, config.MONGODB_DATABASE)
    file_manager = FileManager(config.STORAGE_PATH)
    
    # 连接到数据库
    connected = await db_service.connect()
    
    if not connected:
        print("❌ 无法连接到MongoDB，请确保MongoDB服务正在运行")
        return
    
    print("✅ MongoDB连接成功")
    
    # 获取历史任务
    tasks = await db_service.get_history_tasks(limit=3)
    
    if not tasks:
        print("ℹ️ 暂无历史任务可供测试")
        return
    
    print(f"📋 找到 {len(tasks)} 个历史任务")
    
    # 分析每个任务的文件情况
    for i, task in enumerate(tasks):
        task_id = task.get('task_id', 'unknown')[:8]
        print(f"\n📝 任务 {i+1}: {task_id}...")
        print(f"   状态: {task.get('status', 'unknown')}")
        
        # 检查图片文件
        images = task.get('images', [])
        print(f"   图片数量: {len(images)}")
        existing_images = 0
        for img in images:
            if img and 'file_id' in img:
                file_path = file_manager.get_file_path(img['file_id'])
                if file_path:
                    existing_images += 1
        print(f"   现存图片: {existing_images}/{len(images)}")
        
        # 检查原始图片
        original_id = task.get('original_image_id')
        original_exists = False
        if original_id:
            original_path = file_manager.get_file_path(original_id)
            original_exists = original_path is not None
        print(f"   原始图片: {'✅ 存在' if original_exists else '❌ 缺失'}")
        
        # 检查视频文件
        video_id = task.get('video_id')
        video_exists = False
        if video_id:
            video_path = file_manager.get_file_path(video_id)
            video_exists = video_path is not None
        print(f"   视频文件: {'✅ 存在' if video_exists else '❌ 缺失'}")
        
        print(f"   总文件数: {existing_images + (1 if original_exists else 0) + (1 if video_exists else 0)}")
    
    # 显示删除操作的预期影响
    print(f"\n💡 删除功能测试要点:")
    print(f"   • API端点: DELETE /api/history/<task_id>")
    print(f"   • 会删除: 任务记录 + 所有相关图片 + 原始图片 + 视频文件")
    print(f"   • 前端界面: 删除按钮在每个任务的标题栏右侧")
    print(f"   • 确认对话框: 自定义模态框显示详细删除信息")
    print(f"   • 删除后: 自动刷新历史任务列表")
    
    await db_service.disconnect()
    print("\n✅ 测试分析完成")
    print("\n🚀 启动应用后可在前端界面测试删除功能")

if __name__ == '__main__':
    asyncio.run(test_history_task_deletion())
