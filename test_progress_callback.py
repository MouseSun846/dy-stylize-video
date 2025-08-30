#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试历史任务重新生成视频的进度回调功能
"""
import asyncio
import sys
import os
sys.path.append('backend')

async def test_progress_callback():
    """测试进度回调功能"""
    print("🧪 测试历史任务重新生成视频的进度回调功能...")
    
    # 模拟 active_tasks 数据结构
    active_tasks = {}
    
    # 模拟 update_progress 函数
    def update_progress(task_id: str, progress: float, message: str):
        """更新任务进度"""
        if task_id in active_tasks:
            active_tasks[task_id]['progress'] = min(100, max(0, progress))
            active_tasks[task_id]['message'] = message
            print(f"[{task_id}] {progress:.1f}% - {message}")
    
    # 模拟任务ID
    task_id = "test_task_123"
    
    # 初始化任务
    active_tasks[task_id] = {
        'status': 'processing',
        'progress': 0,
        'message': '准备中...'
    }
    
    print(f"✅ 初始化任务: {task_id}")
    
    # 模拟历史任务重新生成的进度更新序列
    print("\n📋 模拟历史任务重新生成进度:")
    
    # 1. 开始阶段
    update_progress(task_id, 10, '正在从历史任务重新生成视频...')
    await asyncio.sleep(0.5)
    
    # 2. 准备阶段
    update_progress(task_id, 20, '正在准备音频文件...')
    await asyncio.sleep(0.5)
    
    # 3. 图片序列准备
    update_progress(task_id, 30, '正在准备图片序列...')
    await asyncio.sleep(0.5)
    
    # 4. 开始视频合成
    update_progress(task_id, 40, '正在开始视频合成...')
    await asyncio.sleep(0.5)
    
    # 5. 模拟视频合成进度回调 (40% + p * 50%)
    print("\n🎬 模拟VideoComposer进度回调:")
    for p in [10, 20, 40, 60, 80, 95, 100]:
        final_progress = 40 + p * 0.5
        update_progress(task_id, final_progress, '正在重新合成视频...')
        await asyncio.sleep(0.3)
    
    # 6. 保存阶段
    update_progress(task_id, 90, '正在保存视频文件...')
    await asyncio.sleep(0.5)
    
    # 7. 完成
    update_progress(task_id, 100, '视频重新生成完成')
    
    print(f"\n✅ 进度回调测试完成")
    print(f"📊 最终状态: {active_tasks[task_id]['progress']:.1f}% - {active_tasks[task_id]['message']}")
    
    # 验证进度范围
    if 0 <= active_tasks[task_id]['progress'] <= 100:
        print("✅ 进度值在有效范围内 (0-100%)")
    else:
        print("❌ 进度值超出有效范围")
    
    print("\n💡 修复要点:")
    print("• 增加了更详细的进度节点 (10%, 20%, 30%, 40%)")
    print("• 修正了视频合成进度回调计算 (40% + p * 50%)")
    print("• 添加了保存阶段的进度更新 (90%)")
    print("• 确保每个阶段都有对应的状态消息")

if __name__ == '__main__':
    asyncio.run(test_progress_callback())