#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件引用保护功能修复总结报告
=====================================

问题描述：
历史任务重新生成视频时，如果图片路径引用的是其他历史任务的图片文件，
删除历史任务时不应删除这些共享文件，否则会导致其他任务查看详情时图片显示不出来。

修复方案：
1. 实现文件引用检查机制
2. 只删除未被其他任务引用的文件
3. 保护共享文件的完整性

修复内容：
=====================================

✅ 1. 历史任务删除API增强 (DELETE /api/history/{task_id})
   - 在删除前检查所有其他历史任务的文件引用
   - 收集被引用的文件ID集合（图片、原始图片、视频）
   - 只删除未被引用的文件，保留共享文件
   - 详细的日志记录，说明哪些文件被保留、哪些被删除

✅ 2. 新增孤儿文件清理API (POST /api/database/cleanup-orphaned-files)
   - 扫描所有存储目录（uploads, generated, videos）
   - 识别未被任何任务引用的孤儿文件
   - 批量清理无用文件，回收存储空间
   - 提供详细的清理统计信息

✅ 3. 历史任务重新生成进度回调修复
   - 修复了进度回调计算问题
   - 增加了更详细的进度节点
   - 确保用户能看到实时的进度反馈

技术实现细节：
=====================================

引用检查机制：
```python
# 收集其他任务引用的文件ID
referenced_file_ids = set()
for other_task in all_tasks:
    if other_task.get('task_id') != task_id:
        # 收集各类文件ID到引用集合
        if other_task.get('images'):
            for img in other_task['images']:
                if img and 'file_id' in img:
                    referenced_file_ids.add(img['file_id'])
        
        if other_task.get('original_image_id'):
            referenced_file_ids.add(other_task['original_image_id'])
        
        if other_task.get('video_id'):
            referenced_file_ids.add(other_task['video_id'])

# 安全删除检查
if file_id not in referenced_file_ids:
    # 未被引用，可以安全删除
    file_manager.delete_file(file_id)
else:
    # 被其他任务引用，保留文件
    logger.info(f"保留被其他任务引用的文件: {file_id}")
```

进度回调修复：
```python
async def regenerate_video_async(...):
    # 更详细的进度节点
    active_tasks[task_id]['progress'] = 10  # 开始
    active_tasks[task_id]['progress'] = 20  # 准备音频
    active_tasks[task_id]['progress'] = 30  # 准备图片序列
    active_tasks[task_id]['progress'] = 40  # 开始视频合成
    
    # 修正的进度回调计算
    progress_callback=lambda p: update_progress(
        task_id, 40 + p * 0.5, '正在重新合成视频...'
    )
```

API 端点：
=====================================

1. DELETE /api/history/{task_id}
   - 增强的历史任务删除，带引用保护
   - 返回删除的文件列表和保留的文件信息

2. POST /api/database/cleanup-orphaned-files
   - 新增孤儿文件清理端点
   - 返回清理统计信息

测试验证：
=====================================

✅ 测试文件：
- test_file_reference_protection.py - 验证引用保护机制
- test_progress_callback.py - 验证进度回调修复

✅ 验证场景：
1. 共享文件保护 - 多个任务引用同一文件时的保护
2. 独占文件删除 - 仅被单个任务使用的文件正确删除
3. 删除后完整性 - 其他任务的数据完整性验证
4. 进度显示 - 重新生成视频时的实时进度

注意事项：
=====================================

⚠️ 单个图片删除（DELETE /api/images/{image_id}）
   - 当前未实现引用保护
   - 考虑到用户体验，允许删除当前任务中的图片
   - 如需加强保护，可后续添加警告机制

⚠️ 性能考虑
   - 引用检查需要遍历所有历史任务
   - 对于大量历史任务的情况，可考虑建立索引
   - 目前限制获取1000个历史任务进行检查

💡 建议改进：
1. 建立文件引用索引表，提高检查效率
2. 实现文件引用计数缓存机制
3. 添加定期的数据一致性检查任务
4. 考虑实现文件软删除机制（标记删除但保留文件）

部署说明：
=====================================

1. 无需数据库迁移，修改仅涉及API逻辑
2. 建议部署后运行一次孤儿文件清理
3. 监控删除操作的日志，确保引用保护正常工作
4. 如有大量历史数据，首次运行可能较慢

修复完成时间：{当前时间}
修复状态：✅ 完成
影响范围：历史任务管理、文件管理、进度显示
风险评估：低风险，主要是增强数据保护
"""