#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试视频预览功能的修复
验证历史任务是否正确包含video_url字段
"""
import asyncio
import json
from backend.services.database import DatabaseService

async def test_video_preview_fix():
    """测试视频预览修复"""
    print("🧪 测试视频预览功能修复...")
    
    # 连接到数据库
    db_service = DatabaseService("mongodb://localhost:27017", "stylize_video")
    connected = await db_service.connect()
    
    if not connected:
        print("❌ 无法连接到MongoDB，请确保MongoDB服务正在运行")
        return
    
    print("✅ MongoDB连接成功")
    
    # 获取历史任务
    tasks = await db_service.get_history_tasks(limit=5)
    
    if not tasks:
        print("ℹ️ 暂无历史任务")
        return
    
    print(f"📋 找到 {len(tasks)} 个历史任务")
    
    # 检查每个任务是否包含video_url
    for i, task in enumerate(tasks):
        task_id = task.get('task_id', 'unknown')[:8]
        status = task.get('status', 'unknown')
        video_url = task.get('video_url')
        video_id = task.get('video_id')
        
        print(f"📝 任务 {i+1}: {task_id}...")
        print(f"   状态: {status}")
        print(f"   视频URL: {'✅ 存在' if video_url else '❌ 缺失'}")
        print(f"   视频ID: {'✅ 存在' if video_id else '❌ 缺失'}")
        
        if video_url:
            print(f"   URL: {video_url}")
        
        print()
    
    await db_service.disconnect()
    print("✅ 测试完成")

if __name__ == '__main__':
    asyncio.run(test_video_preview_fix())